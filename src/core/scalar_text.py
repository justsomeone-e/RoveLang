"""Generated scalar-text helpers shared by HIR and MIR backends."""

RUST_F64_RUNTIME = r'''
fn _rove_f64_to_string(value: f64) -> String {
    if value.is_nan() { return "nan".to_string(); }
    if value == f64::INFINITY { return "inf".to_string(); }
    if value == f64::NEG_INFINITY { return "-inf".to_string(); }
    if value == 0.0 { return "0".to_string(); }
    let text = value.to_string();
    let (negative, body) = if let Some(body) = text.strip_prefix('-') {
        (true, body)
    } else {
        (false, text.as_str())
    };
    let (mantissa, exponent) = if let Some(marker) = body.find(|c: char| c == 'e' || c == 'E') {
        (&body[..marker], body[marker + 1..].parse::<i32>().expect("Rove float exponent"))
    } else {
        (body, 0)
    };
    let dot = mantissa.find('.').unwrap_or(mantissa.len());
    let digits = mantissa.replace('.', "");
    let first = digits.len() - digits.trim_start_matches('0').len();
    let decimal = dot as i32 + exponent - first as i32;
    let digits = digits[first..].trim_end_matches('0');
    let rendered = if decimal > -6 && decimal <= 21 {
        if decimal <= 0 {
            format!("0.{}{}", "0".repeat((-decimal) as usize), digits)
        } else if decimal as usize >= digits.len() {
            format!("{}{}", digits, "0".repeat(decimal as usize - digits.len()))
        } else {
            format!("{}.{}", &digits[..decimal as usize], &digits[decimal as usize..])
        }
    } else {
        let fraction = if digits.len() > 1 { format!(".{}", &digits[1..]) }
                       else { String::new() };
        let exponent = decimal - 1;
        format!("{}{}e{}{}", &digits[..1], fraction,
                if exponent >= 0 { "+" } else { "" }, exponent)
    };
    if negative { format!("-{rendered}") } else { rendered }
}
'''
