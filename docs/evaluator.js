// Limited teaching evaluator. This is not the Rove compiler.
(function () {
  function checkCommonSyntaxErrors(code) {
    const lines = code.split('\n');
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      const lineNum = i + 1;

      // Detect escape sequences mistakenly typed outside quotes: e.g. "foo"\n or "bar"\t
      if (/"[^"]*"\\[a-zA-Z]/.test(line) || /"[^"]*"\s*\\[a-zA-Z]/.test(line)) {
        return `Syntax Error (Line ${lineNum}): Escape sequence (like \\n) found outside of quotation marks.\n  Did you mean to place it inside the string? e.g. "Hello\\n" instead of "Hello"\\n`;
      }

      // Detect unclosed quotation marks on single lines (ignoring comments)
      const codeWithoutComment = line.replace(/\/\/.*$/, '');
      const quotes = (codeWithoutComment.match(/(?<!\\)"/g) || []).length;
      if (quotes % 2 !== 0 && !codeWithoutComment.includes('"""')) {
        return `Syntax Error (Line ${lineNum}): Unterminated string literal. Check that your string has matching quotes.\n  Line: ${line.trim()}`;
      }
    }
    return null;
  }

  function evaluateRove(source) {
    // Check syntax errors first for friendly diagnostics
    const preSyntaxError = checkCommonSyntaxErrors(source);
    if (preSyntaxError) {
      return { output: [], error: preSyntaxError };
    }

    // Rove examples call main() explicitly. Only synthesize the entry-point
    // call when the source defines main without an explicit top-level call.
    const sourceWithoutMainDefinition = source.replace(/\bfn\s+main\s*\([^)]*\)/g, '');
    const hasExplicitMainCall = /\bmain\s*\([ \t]*\)/.test(sourceWithoutMainDefinition);

    const output = [];
    const printFn = (...args) => {
      output.push(args.map(a => formatValue(a)).join(' '));
    };

    let jsCode = source
      // Strip comments
      .replace(/\/\/[^\n]*$/gm, '')
      // Directives
      .replace(/#target\s+\w+/g, '')
      .replace(/#native\s+include\s+<[^>]+>/g, '')
      // Imports
      .replace(/\bimport\s+\{([^}]+)\}\s+from\s+"[^"]+"/g, (m, syms) => {
        return syms.split(',').map(s => s.trim()).filter(Boolean).map(s => {
          if (s === 'sin') return 'const sin = Math.sin;';
          if (s === 'cos') return 'const cos = Math.cos;';
          if (s === 'sqrt') return 'const sqrt = Math.sqrt;';
          if (s === 'PI') return 'const PI = Math.PI;';
          return `/* imported ${s} */`;
        }).join(' ');
      })
      .replace(/\bimport\s+[^;\n]+;?/g, '')
      // Traits
      .replace(/\btrait\s+[a-zA-Z0-9_]+\s*\{[^}]*\}/g, '')
      // Tests: test "description" { ... }
      .replace(/\btest\s+"([^"]+)"\s*\{([^}]*)\}/g, '(() => { print("TEST: " + "$1"); $2 })();')
      // Guard: guard cond else { body }
      .replace(/\bguard\s+([^{]+)\s+else\s*\{([^}]+)\}/g, 'if (!($1)) { $2 }')
      // Loop: loop { ... }
      .replace(/\bloop\s*\{/g, 'while (true) {')
      // Catch: catch err { ... }
      .replace(/\bcatch\s+([a-zA-Z0-9_]+)\s*\{/g, 'catch ($1) {')
      // Impl blocks
      .replace(/\bimpl(?:\s+[a-zA-Z0-9_]+\s+for)?\s+([a-zA-Z0-9_]+)\s*\{([\s\S]*?)\n\}/g, (m, structName, body) => {
        return body.replace(/\bfn\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)(?:\s*->\s*[^{]+)?\s*\{/g, (f, fnName, args) => {
          const cleanArgs = args.replace(/\bself\b,?\s*/, '')
            .replace(/:\s*[a-zA-Z0-9_?<>]+(\s*=)?/g, '$1')
            .trim();
          return `${structName}.prototype.${fnName} = function(${cleanArgs}) { const self = this;`;
        });
      })
      // Match expressions & statements
      .replace(/(=|return|^|\n)\s*match\s+([^{]+)\s*\{([\s\S]*?)\n\s*\}/g, (match, prefix, subject, arms) => {
        const isExpr = prefix.trim() === '=' || prefix.trim() === 'return';
        let armStatements = [];
        const lines = arms.split('\n');
        for (const rawLine of lines) {
          const line = rawLine.trim().replace(/,$/, '');
          if (!line) continue;
          const arrowIdx = line.indexOf('=>');
          if (arrowIdx !== -1) {
            const pat = line.substring(0, arrowIdx).trim();
            let expr = line.substring(arrowIdx + 2).trim();
            if (isExpr && !expr.startsWith('return ')) {
              expr = `return (${expr});`;
            } else if (!expr.endsWith(';')) {
              expr += ';';
            }
            
            if (pat === '_') {
              armStatements.push(expr);
            } else if (/^Ok\(([a-zA-Z0-9_]+)\)$/.test(pat)) {
              const varName = pat.match(/^Ok\(([a-zA-Z0-9_]+)\)$/)[1];
              armStatements.push(`if (__subj && __subj.is_ok) { const ${varName} = __subj.value; ${expr} }`);
            } else if (/^Err\(([a-zA-Z0-9_]+)\)$/.test(pat)) {
              const varName = pat.match(/^Err\(([a-zA-Z0-9_]+)\)$/)[1];
              armStatements.push(`if (__subj && __subj.is_ok === false) { const ${varName} = __subj.error; ${expr} }`);
            } else if (/^([A-Z][a-zA-Z0-9_]*)\(([^)]*)\)$/.test(pat)) {
              const m = pat.match(/^([A-Z][a-zA-Z0-9_]*)\(([^)]*)\)$/);
              const tag = m[1];
              const inner = m[2].trim();
              if (inner) {
                armStatements.push(`if (__subj && __subj._tag === "${tag}") { const ${inner} = __subj._val; ${expr} }`);
              } else {
                armStatements.push(`if (__subj && __subj._tag === "${tag}") { ${expr} }`);
              }
            } else {
              armStatements.push(`if (__subj == ${pat}) { ${expr} }`);
            }
          }
        }

        if (isExpr) {
          return `${prefix} ((() => { const __subj = (${subject}); ${armStatements.join(' ')} })())`;
        } else {
          return `(() => { const __subj = (${subject}); ${armStatements.join(' ')} })();`;
        }
      })
      // Enums
      .replace(/\benum\s+([a-zA-Z0-9_]+)\s*\{([^}]*)\}/g, (m, name, variants) => {
        const lines = variants.split(',').map(v => v.trim()).filter(Boolean);
        const ctors = lines.map(v => {
          if (v.includes('(')) {
            const vname = v.substring(0, v.indexOf('(')).trim();
            return `const ${vname} = (val) => ({ _enum: "${name}", _tag: "${vname}", _val: val });`;
          } else {
            return `const ${v} = { _enum: "${name}", _tag: "${v}" };`;
          }
        }).join(' ');
        return `const ${name} = {}; ${ctors}`;
      })
      // Structs
      .replace(/\bstruct\s+([a-zA-Z0-9_]+)\s*\{([^}]*)\}/g, (m, name, fields) => {
        const fieldNames = fields.split(',').map(f => f.trim()).filter(Boolean).map(f => f.split(':')[0].trim());
        return `function ${name}(init = {}) {
          if (!(this instanceof ${name})) return new ${name}(init);
          ${fieldNames.map(f => `this.${f} = init.${f};`).join('\n')}
        }`;
      })
      // Defer
      .replace(/\bdefer\s+([^;\n]+);?/g, '__defers.push(() => { $1; });')
      // Set assignments: set x = y -> x = y
      .replace(/\bset\s+([a-zA-Z0-9_.[\]]+)\s*=/g, '$1 =')
      // Let & Var
      .replace(/\blet\s+mut\s+/g, 'let ')
      .replace(/\blet\s+([a-zA-Z0-9_]+)(?::\s*[a-zA-Z0-9_?<>]+)?\s*=/g, 'let $1 =')
      .replace(/\bvar\s+([a-zA-Z0-9_]+)(?::\s*[a-zA-Z0-9_?<>]+)?\s*=/g, 'let $1 =')
      // Single-line functions: fn foo(a: int) -> int = a * 2
      .replace(/\bfn\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)(?:\s*->\s*[^{=]+)?\s*=\s*([^;\n]+)/g, (m, name, args, expr) => {
        const cleanArgs = args.split(',').map(a => a.split(':')[0].trim()).filter(Boolean).join(', ');
        return `function ${name}(${cleanArgs}) { return (${expr}); }`;
      })
      // Block functions: fn foo(a: int) -> int { ... }
      .replace(/\bfn\s+([a-zA-Z0-9_]+)\s*\(([^)]*)\)(?:\s*->\s*[^{]+)?\s*\{/g, (m, name, args) => {
        const cleanArgs = args.split(',').map(a => a.split(':')[0].trim()).filter(Boolean).join(', ');
        return `function ${name}(${cleanArgs}) { const __defers = []; try {`;
      })
      // Close functions with defer execution
      .replace(/\}\s*(\n|$)/g, (m) => {
        return '} finally { if (typeof __defers !== "undefined") { while(__defers.length) { try { __defers.pop()(); } catch(e){} } } } }\n';
      })
      // String Interpolation: $"val is {x}" -> `val is ${x}`
      .replace(/\$"([^"\\]*(?:\\.[^"\\]*)*)"/g, (m, inner) => {
        const converted = inner.replace(/\{([^}]+)\}/g, '${$1}');
        return '`' + converted + '`';
      })
      // Null coalescing: ??
      .replace(/\?\?/g, '??')
      // Logical keywords
      .replace(/\band\b/g, '&&')
      .replace(/\bor\b/g, '||')
      .replace(/\bnot\b/g, '!');

    // Pipeline chains: a |> b |> c -> c(b(a))
    let prevPipe = '';
    while (prevPipe !== jsCode) {
      prevPipe = jsCode;
      jsCode = jsCode.replace(/([a-zA-Z0-9_.[\]()]+)\s*\|>\s*([a-zA-Z0-9_]+)/g, '$2($1)');
    }

    let runner;
    try {
      runner = new Function('print', 'assert', 'len', 'map', 'filter', 'fold', 'Ok', 'Err', 'base64_encode', 'base64_decode', 'get_string', 'get_int', `
        try {
          ${jsCode}
          if (typeof main === 'function' && ${!hasExplicitMainCall}) {
            main();
          }
        } catch(e) {
          return { error: e.message };
        }
      `);
    } catch (err) {
      const msg = err.message || '';
      let friendly = `Compilation Error: ${msg}`;
      if (msg.includes('invalid escape sequence')) {
        friendly = "Syntax Error: Invalid escape sequence. Check your string quotes to make sure escapes like '\\n' are inside quotes, not outside.";
      } else if (msg.includes('Unexpected token')) {
        friendly = `Syntax Error: ${msg}. Check for missing parentheses, quotes, or semicolons.`;
      }
      return { output: [], error: friendly };
    }

    const assertFn = (cond, msg) => {
      if (!cond) throw new Error(msg || 'Assertion failed');
    };
    const lenFn = (x) => (x ? (x.length !== undefined ? x.length : (x.size !== undefined ? x.size : 0)) : 0);
    const mapFn = (arr, fn) => (Array.isArray(arr) ? arr.map(fn) : []);
    const filterFn = (arr, fn) => (Array.isArray(arr) ? arr.filter(fn) : []);
    const foldFn = (arr, init, fn) => (Array.isArray(arr) ? arr.reduce((acc, x) => fn(acc, x), init) : init);
    const okHelper = (v) => ({ is_ok: true, value: v, unwrap: () => v, toString: () => `Ok(${v})` });
    const errHelper = (e) => ({ is_ok: false, error: e, unwrap: () => { throw new Error(e); }, toString: () => `Err("${e}")` });
    const b64enc = (s) => {
      try { return btoa(unescape(encodeURIComponent(String(s)))); } catch(e) { return ''; }
    };
    const b64dec = (s) => {
      try {
        if (/[^A-Za-z0-9+/=]/.test(s)) return errHelper('malformed base64');
        const res = decodeURIComponent(escape(atob(s)));
        return okHelper(res);
      } catch(e) {
        return errHelper('malformed base64');
      }
    };
    const getStr = (doc, key) => {
      try {
        const obj = typeof doc === 'string' ? JSON.parse(doc) : doc;
        if (obj && obj[key] !== undefined) return okHelper(String(obj[key]));
        return errHelper('key not found');
      } catch(e) { return errHelper(e.message); }
    };
    const getNum = (doc, key) => {
      try {
        const obj = typeof doc === 'string' ? JSON.parse(doc) : doc;
        if (obj && obj[key] !== undefined) return okHelper(Number(obj[key]));
        return errHelper('key not found');
      } catch(e) { return errHelper(e.message); }
    };

    const res = runner(printFn, assertFn, lenFn, mapFn, filterFn, foldFn, okHelper, errHelper, b64enc, b64dec, getStr, getNum);
    return { output, error: res ? res.error : null };
  }

  function formatValue(v) {
    if (v === null || v === undefined) return 'null';
    if (typeof v === 'object' && v.is_ok !== undefined) {
      return v.is_ok ? `Ok(${v.value})` : `Err("${v.error}")`;
    }
    if (Array.isArray(v)) {
      return '[' + v.map(formatValue).join(', ') + ']';
    }
    return String(v);
  }


  globalThis.RovePreview = { evaluateRove };
})();
