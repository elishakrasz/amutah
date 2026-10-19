import copy
from typing import Any

from app.domain.config import RulesConfig, parse_config
from app.scripts.demo_config import CONFIG_V1

POVERTY_LINE = CONFIG_V1["scoring"]["poverty_line_monthly_agorot"]  # ₪3,547 (Q22)
MONTHLY_BUDGET = 5_000_000  # synthetic ₪50,000


def body(**overrides: Any) -> dict[str, Any]:
    """CONFIG_V1 with the budget placeholder filled and dotted-path overrides,
    e.g. body(**{"caps.per_grant": 1})."""
    b = copy.deepcopy(CONFIG_V1)
    b["budget"]["monthly_allocation"] = MONTHLY_BUDGET
    for path, value in overrides.items():
        node = b
        *parents, leaf = path.split(".")
        for p in parents:
            node = node[p]
        if value is DELETE:
            del node[leaf]
        else:
            node[leaf] = value
    return b


DELETE = object()


def cfg(**overrides: Any) -> RulesConfig:
    return parse_config(1, body(**overrides))
