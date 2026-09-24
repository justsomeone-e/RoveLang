"""Canonical builtin signatures shared by HIR lowering and verification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from .types import ANY, BOOL, INT, STRING, VOID, IRType, array_of, function_type


@dataclass(frozen=True, slots=True)
class BuiltinSignature:
    parameters: Tuple[IRType, ...]
    result: IRType
    min_args: int
    max_args: Optional[int]

    @property
    def type(self) -> IRType:
        return function_type(self.parameters, self.result)


def _exact(parameters: Tuple[IRType, ...], result: IRType) -> BuiltinSignature:
    return BuiltinSignature(parameters, result, len(parameters), len(parameters))


BUILTINS: Dict[str, BuiltinSignature] = {
    "print": BuiltinSignature((), VOID, 0, None),
    "input": BuiltinSignature((STRING,), STRING, 0, 1),
    "to_string": _exact((ANY,), STRING),
    "to_int": _exact((STRING,), INT),
    "contains": _exact((STRING, STRING), BOOL),
    "is_number": _exact((STRING,), BOOL),
    "addr": _exact((ANY,), IRType("uintptr")),
    "peek": _exact((IRType("uintptr"),), IRType("uintptr")),
    "memdump": _exact((IRType("uintptr"), INT), VOID),
    "delay_ms": _exact((INT,), VOID),
    "channel": BuiltinSignature((), IRType("Channel"), 0, 1),
    "Ok": _exact((ANY,), IRType("Result", (ANY, ANY))),
    "Err": _exact((ANY,), IRType("Result", (ANY, ANY))),
    "len": _exact((ANY,), INT),
    "args": _exact((), array_of(STRING)),
    "map": _exact((ANY, ANY), ANY),
    "filter": _exact((ANY, ANY), ANY),
    "fold": _exact((ANY, ANY, ANY), ANY),
}


BUILTIN_TYPES: Dict[str, IRType] = {
    name: signature.type for name, signature in BUILTINS.items()
}


# Private runtime calls used by stdlib wrappers. Keeping the signatures here,
# rather than inferring declarations from target-specific ``#native raw`` text,
# gives every frontend and verifier one target-neutral ABI contract.
INTRINSICS: Dict[str, BuiltinSignature] = {
    "_rove_destructure_check": _exact((ANY, INT, STRING), ANY),
    "_rove_bootstrap_read_file": _exact((STRING,), STRING),
    "_rove_bootstrap_write_file": _exact((STRING, STRING), BOOL),
    "_rove_bootstrap_file_exists": _exact((STRING,), BOOL),
    "_rove_bootstrap_remove_file": _exact((STRING,), BOOL),
    "_rove_process_exit": _exact((INT,), VOID),
    "_rove_toolchain_compile_cpp": _exact((STRING, STRING), INT),
    "_rove_toolchain_last_error": _exact((), STRING),
    "_rove_utf8_from_codepoint": _exact((INT,), STRING),
    "_rove_math_sin": _exact((IRType("float"),), IRType("float")),
    "_rove_math_cos": _exact((IRType("float"),), IRType("float")),
    "_rove_math_tan": _exact((IRType("float"),), IRType("float")),
    "_rove_math_sqrt": _exact((IRType("float"),), IRType("float")),
    "_rove_math_pow": _exact((IRType("float"), IRType("float")), IRType("float")),
    "_rove_math_abs": _exact((IRType("float"),), IRType("float")),
    "_rove_math_floor": _exact((IRType("float"),), IRType("float")),
    "_rove_math_ceil": _exact((IRType("float"),), IRType("float")),
    "_rove_math_round": _exact((IRType("float"),), IRType("float")),
    "_rove_math_clamp": _exact(
        (IRType("float"), IRType("float"), IRType("float")),
        IRType("float"),
    ),
    "_rove_time_now_ms": _exact((), INT),
    "_rove_time_now_us": _exact((), INT),
    "_rove_time_sleep_ms": _exact((INT,), VOID),
    "_rove_base64_encode": _exact((STRING,), STRING),
    "_rove_base64_decode": _exact((STRING,), STRING),
    "_rove_base64_decode_result": _exact((STRING,), IRType("Result", (STRING, STRING))),
    "_rove_hash_fnv1a_64_hex": _exact((STRING,), STRING),
    "_rove_fs_read_to_string": _exact((STRING,), STRING),
    "_rove_fs_write_string": _exact((STRING, STRING), BOOL),
    "_rove_fs_append_string": _exact((STRING, STRING), BOOL),
    "_rove_fs_exists": _exact((STRING,), BOOL),
    "_rove_fs_remove_file": _exact((STRING,), BOOL),
    "_rove_fs_read_to_string_result": _exact((STRING,), IRType("Result", (STRING, STRING))),
    "_rove_fs_write_string_result": _exact((STRING, STRING), IRType("Result", (BOOL, STRING))),
    "_rove_fs_append_string_result": _exact((STRING, STRING), IRType("Result", (BOOL, STRING))),
    "_rove_fs_remove_file_result": _exact((STRING,), IRType("Result", (BOOL, STRING))),
    "_rove_json_get_string": _exact((STRING, STRING), STRING),
    "_rove_json_get_int": _exact((STRING, STRING), INT),
    "_rove_json_get_string_result": _exact((STRING, STRING), IRType("Result", (STRING, STRING))),
    "_rove_json_get_int_result": _exact((STRING, STRING), IRType("Result", (INT, STRING))),
    "_rove_json_get_string_full": _exact((STRING, STRING), STRING),
    "_rove_json_get_int_full": _exact((STRING, STRING), INT),
    "_rove_json_get_bool_full": _exact((STRING, STRING), BOOL),
    "_rove_json_has_key": _exact((STRING, STRING), BOOL),
    "_rove_json_escape": _exact((STRING,), STRING),
    "_rove_net_tcp_connect": _exact((STRING, INT), INT),
    "_rove_net_tcp_send": _exact((INT, STRING), BOOL),
    "_rove_net_tcp_recv": _exact((INT, INT), STRING),
    "_rove_net_tcp_close": _exact((INT,), VOID),
    "_rove_net_tcp_connect_result": _exact((STRING, INT), IRType("Result", (INT, STRING))),
    "_rove_net_tcp_send_result": _exact((INT, STRING), IRType("Result", (BOOL, STRING))),
    "_rove_net_tcp_recv_result": _exact((INT, INT), IRType("Result", (STRING, STRING))),
    "_rove_net_tcp_close_result": _exact((INT,), IRType("Result", (BOOL, STRING))),
    "_rove_mutex_create": _exact((), INT),
    "_rove_mutex_lock": _exact((INT,), VOID),
    "_rove_mutex_unlock": _exact((INT,), VOID),
    "_rove_channel_create": _exact((), INT),
    "_rove_channel_send": _exact((INT, STRING), VOID),
    "_rove_channel_recv": _exact((INT,), STRING),
    "_rove_process_exec_cmd_result": _exact((STRING,), IRType("Result", (INT, STRING))),
    "_rove_process_get_env_result": _exact((STRING,), IRType("Result", (STRING, STRING))),
    "_rove_path_join": _exact((STRING, STRING), STRING),
    "_rove_path_basename": _exact((STRING,), STRING),
    "_rove_path_dirname": _exact((STRING,), STRING),
    "_rove_path_extname": _exact((STRING,), STRING),
    "_rove_path_is_abs": _exact((STRING,), BOOL),
    "_rove_path_normalize": _exact((STRING,), STRING),
    "_rove_str_trim": _exact((STRING,), STRING),
    "_rove_str_starts_with": _exact((STRING, STRING), BOOL),
    "_rove_str_ends_with": _exact((STRING, STRING), BOOL),
    "_rove_str_find_result": _exact((STRING, STRING), IRType("Result", (INT, STRING))),
    "_rove_str_to_upper": _exact((STRING,), STRING),
    "_rove_str_to_lower": _exact((STRING,), STRING),
    "_rove_str_replace": _exact((STRING, STRING, STRING), STRING),
}


INTRINSIC_TYPES: Dict[str, IRType] = {
    name: signature.type for name, signature in INTRINSICS.items()
}
