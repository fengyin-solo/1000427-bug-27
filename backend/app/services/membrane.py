"""膜组件业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "membrane"
REQUIRED_FIELDS = ["膜组编号", "膜型号", "膜面积"]
ALL_FIELDS = ["膜组编号", "膜型号", "膜面积", "跨膜压差", "通量", "清洗周期", "投用日期"]
STATUS_ORDER = ["待投用", "运行中", "待清洗", "已更换"]
ACTION_RULES = {"确认投用": "运行中", "提交清洗": "待清洗", "更换膜组": "已更换"}
NEGATIVE_ACTIONS = []
# 终态：已更换的旧膜组只能归档查看，不能再执行任何动作
FINAL_STATUS = "已更换"
# 各状态允许执行的动作；未列入的一律拦截，避免状态被来回改写
ALLOWED_ACTIONS: dict[str, list[str]] = {
    "待投用": ["确认投用", "更换膜组"],
    "运行中": ["提交清洗", "更换膜组"],
    "待清洗": ["确认投用", "更换膜组"],
    "已更换": [],
}
# 更换膜组后，旧膜组随本体退役的运行数据要清空，避免新膜组继承旧读数
RESET_ON_REPLACE = ["膜面积", "跨膜压差", "通量"]
DISPLAY_STATUS_FIELD = "膜组状态"
PRESSURE_FIELD = "跨膜压差"


class MembraneService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("膜组编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        for field in ALL_FIELDS:
            value = values.get(field)
            entry[field] = None if value is None or not str(value).strip() else value
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        # 展示用的「膜组状态」列与内部状态始终同源，避免列表与详情口径不一致
        entry[DISPLAY_STATUS_FIELD] = entry["status"]
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"膜组 {entry_id} 不存在或已归档，无法执行该操作"
        action = (action or "").strip()
        if not action:
            return None, "未指定要执行的动作，请选择确认投用、提交清洗或更换膜组"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于膜组件可执行范围"
        current = str(entry.get("status") or "")
        target = ACTION_RULES[action]
        if current == FINAL_STATUS:
            return None, f"膜组{entry.get('膜组编号', entry_id)}已更换并归档，不能再{action}；如需投用请登记新膜组"
        if action not in ALLOWED_ACTIONS.get(current, []):
            return None, f"膜组{entry.get('膜组编号', entry_id)}当前为「{current}」，不能{action}"
        if current == target:
            return None, f"膜组{entry.get('膜组编号', entry_id)}已是「{current}」状态，无需重复{action}"
        entry["status"] = target
        entry["pending"] = target != FINAL_STATUS
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        entry[DISPLAY_STATUS_FIELD] = target
        if action == "更换膜组":
            for field in RESET_ON_REPLACE:
                entry[field] = None
            return entry, "膜组已更换，旧膜面积、跨膜压差、通量已清空；登记新膜组并确认投用后恢复运行"
        return entry, f"膜组已{action}，状态更新为「{target}」"

    def stats(self) -> list[dict[str, Any]]:
        """膜组件统计卡片：口径与列表同源，全部基于当前全量记录实时计算。"""
        rows = store.rows(MODULE)
        running = sum(1 for row in rows if row.get("status") == "运行中")
        awaiting_wash = sum(1 for row in rows if row.get("status") == "待清洗")
        replaced = sum(1 for row in rows if row.get("status") == FINAL_STATUS)
        pressures = [value for value in (_to_number(row.get(PRESSURE_FIELD)) for row in rows) if value is not None]
        pressure_avg = round(sum(pressures) / len(pressures), 2) if pressures else 0
        return [
            {"label": "膜组总数", "value": len(rows)},
            {"label": "运行膜组", "value": running},
            {"label": "待清洗膜组", "value": awaiting_wash},
            {"label": "已更换膜组", "value": replaced},
            {"label": "跨膜压差均值", "value": pressure_avg},
        ]


def _to_number(value: Any) -> float | None:
    """跨膜压差可能缺失或不是数值（如样例文本），这些记录不参与均值统计。"""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
