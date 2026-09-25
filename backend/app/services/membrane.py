"""膜组件业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "membrane"
REQUIRED_FIELDS = ["膜组编号", "膜型号", "膜面积"]
STATUS_ORDER = ["待投用", "运行中", "待清洗", "已更换"]
ACTION_RULES = {"确认投用": "运行中", "提交清洗": "待清洗", "更换膜组": "已更换"}
NEGATIVE_ACTIONS = ["更换膜组"]
TERMINAL_STATUS = "已更换"
# 每个动作允许的起始状态；已更换是终态，单独拦截并给出说明。
ACTION_SOURCES = {
    "确认投用": {"待投用", "待清洗"},
    "提交清洗": {"运行中"},
    "更换膜组": {"待投用", "运行中", "待清洗"},
}
# 更换后旧膜组的运行参数随之作废，不能继续留在记录里。
REPLACE_RESET_FIELDS = ["跨膜压差", "膜面积"]


class MembraneService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        model: str | None = None,
        area: str | None = None,
    ) -> list[dict[str, Any]]:
        """列表与统计共用的筛选口径，保证两边看到同一批数据。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("膜组编号", ""))]
        if model:
            rows = [row for row in rows if model in str(row.get("膜型号", ""))]
        if area:
            rows = [row for row in rows if area in str(row.get("膜面积", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        model: str | None = None,
        area: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(keyword=keyword, status=status, model=model, area=area)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def stats(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        model: str | None = None,
        area: str | None = None,
    ) -> dict[str, Any]:
        """统计卡片数据：与列表走同一套筛选，更换动作生效后这里立即变化。"""
        rows = self._filter_rows(keyword=keyword, status=status, model=model, area=area)
        tmp_values: list[float] = []
        for row in rows:
            try:
                tmp_values.append(float(row.get("跨膜压差")))
            except (TypeError, ValueError):
                continue
        return {
            "total": len(rows),
            "running": sum(1 for row in rows if row.get("status") == "运行中"),
            "pending_clean": sum(1 for row in rows if row.get("status") == "待清洗"),
            "replaced": sum(1 for row in rows if row.get("status") == TERMINAL_STATUS),
            "avg_tmp": round(sum(tmp_values) / len(tmp_values), 2) if tmp_values else None,
            "tmp_samples": len(tmp_values),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"膜组 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于膜组件可执行范围"
        code = entry.get("膜组编号") or entry_id
        current = str(entry.get("status") or "")
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        if current == TERMINAL_STATUS:
            if action == "更换膜组":
                return None, f"膜组 {code} 已是「已更换」状态，请勿重复更换；如需再次更换请先登记新膜组"
            return None, f"膜组 {code} 已更换下线，不能再执行「{action}」；如需投用请登记新膜组"
        if current == target:
            return None, f"膜组 {code} 已处于「{target}」状态，请勿重复{action}"
        if current not in ACTION_SOURCES[action]:
            return None, f"膜组 {code} 当前状态为「{current}」，不能执行「{action}」"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        if action == "更换膜组":
            for field in REPLACE_RESET_FIELDS:
                entry[field] = None
            return entry, f"膜组 {code} 已更换，旧膜组的跨膜压差、膜面积已清空，概览异常量已同步"
        return entry, f"膜组 {code} 已{action}"
