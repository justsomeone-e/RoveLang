import sys
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Optional


_exit_on_error_override = ContextVar("rove_exit_on_error", default=None)
_emit_output_override = ContextVar("rove_emit_diagnostic_output", default=None)

class DiagnosticError(Exception):
    def __init__(
        self,
        code: str,
        title: str,
        filepath: str,
        line: int,
        col: int,
        formatted_msg: str,
        length: int = 1,
        expected: str = "",
        found: str = "",
        help_msg: str = "",
        searched: Optional[list] = None,
        note: str = "",
    ):
        super().__init__(formatted_msg)
        self.code = code
        self.title = title
        self.filepath = filepath
        self.line = line
        self.col = col
        self.formatted_msg = formatted_msg
        self.length = max(1, length)
        self.expected = expected
        self.found = found
        self.help_msg = help_msg
        self.searched = list(searched or [])
        self.note = note

    def to_dict(self) -> dict:
        return {
            "severity": "error",
            "code": self.code,
            "message": self.title,
            "path": self.filepath,
            "line": self.line,
            "column": self.col,
            "length": self.length,
            "expected": self.expected,
            "found": self.found,
            "help": self.help_msg,
            "searched": self.searched,
            "note": self.note,
        }

class DiagnosticEmitter:
    EXIT_ON_ERROR = True  # Can be disabled by test suites

    @classmethod
    @contextmanager
    def scoped(cls, exit_on_error: Optional[bool] = None, emit_output: Optional[bool] = None):
        """Apply re-entrant, task-local diagnostic behavior for library consumers."""
        inherited_exit = _exit_on_error_override.get()
        inherited_output = _emit_output_override.get()
        exit_token = _exit_on_error_override.set(
            inherited_exit if exit_on_error is None else exit_on_error
        )
        output_token = _emit_output_override.set(
            inherited_output if emit_output is None else emit_output
        )
        try:
            yield
        finally:
            _exit_on_error_override.reset(exit_token)
            _emit_output_override.reset(output_token)

    @classmethod
    def emit_error(
        cls,
        filepath: str,
        source: str,
        line: int,
        col: int,
        code: str,
        title: str,
        length: int = 1,
        expected: str = "",
        found: str = "",
        help_msg: str = "",
        searched: list = None,
        note: str = ""
    ):
        lines = source.splitlines() if source else []
        line_content = lines[line - 1] if 0 < line <= len(lines) else ""
        
        # Calculate caret span width
        caret_len = max(1, length)
        pointer = " " * max(0, col - 1) + "^" * caret_len

        out = []
        out.append(f"\n\033[91m\033[1merror[{code}]: {title}\033[0m")
        out.append(f"  \033[94m-->\033[0m {filepath}:{line}:{col}")
        out.append(f"   \033[94m|\033[0m")
        if line_content:
            out.append(f"\033[94m{line:2d} |\033[0m {line_content}")
            out.append(f"   \033[94m|\033[0m \033[91m{pointer}\033[0m")
            out.append(f"   \033[94m|\033[0m")
            
        if expected or found:
            if expected:
                out.append(f"   \033[94m=\033[0m \033[1mexpected:\033[0m \033[92m{expected}\033[0m")
            if found:
                out.append(f"   \033[94m=\033[0m \033[1mfound:   \033[0m \033[91m{found}\033[0m")
                
        if searched:
            out.append(f"   \033[94m=\033[0m \033[1msearched paths:\033[0m")
            for p in searched:
                out.append(f"       • {p}")
                
        if note:
            out.append(f"   \033[94m=\033[0m \033[93m\033[1mnote:\033[0m {note}")

        if help_msg:
            out.append(f"   \033[94m=\033[0m \033[96m\033[1mhelp:\033[0m {help_msg}")
            
        out.append("")
        formatted = "\n".join(out)
        emit_output = _emit_output_override.get()
        if emit_output is None:
            emit_output = True
        if emit_output:
            print(formatted)
        
        exit_on_error = _exit_on_error_override.get()
        if exit_on_error is None:
            exit_on_error = cls.EXIT_ON_ERROR
        if exit_on_error:
            sys.exit(1)
        else:
            raise DiagnosticError(
                code, title, filepath, line, col, formatted,
                length=length,
                expected=expected,
                found=found,
                help_msg=help_msg,
                searched=searched,
                note=note,
            )

    @classmethod
    def emit_warning(cls, filepath: str, line: int, col: int, code: str, msg: str, help_msg: str = ""):
        emit_output = _emit_output_override.get()
        if emit_output is False:
            return
        print(f"\033[93m\033[1mwarning[{code}]:\033[0m {msg} (at {filepath}:{line}:{col})")
        if help_msg:
            print(f"   \033[94m=\033[0m \033[96m\033[1mhelp:\033[0m {help_msg}")
