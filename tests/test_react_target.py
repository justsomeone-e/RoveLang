import sys, os
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

from src.core.lexer import Lexer
from src.core.parser import Parser
from src.codegen.codegen import UniversalCodeGen

def test_react_generation():
    src = """#target react

var counter = 0
var status = "Online"

fn increment() {
    counter = counter + 1
}

fn reset() {
    counter = 0
}

print("Initial load complete")
"""
    tokens = Lexer(src, "test.rove").tokenize()
    ast = Parser(tokens, "test.rove").parse()
    tsx = UniversalCodeGen(ast).gen_react()
    print("--- GENERATED REACT 19 TSX ---")
    print(tsx)
    print("-------------------------------")
    assert "const [counter, setCounter] = useState" in tsx
    assert "const [status, setStatus] = useState" in tsx
    assert "const increment = () =>" in tsx
    assert "const reset = () =>" in tsx
    assert "Run increment()" in tsx
    assert "Run reset()" in tsx
    assert "Live Output Stream" in tsx
    print("[PASS] react generator produces full reactive React 19 TSX components!")

if __name__ == "__main__":
    test_react_generation()