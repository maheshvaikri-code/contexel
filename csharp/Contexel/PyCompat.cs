using System.Globalization;
using System.Text;

namespace Contexel;

/// <summary>
/// Python-semantics helpers — the parity layer under Stages/Tokens/Trace.
/// Each member replicates the exact CPython behavior the canon relies on
/// (design proven by the TS port's adversarial fuzzing: 118k rounding
/// cases, 50k serialized doubles, zero mismatches). Remaining margins are
/// documented in ADR-002.
/// </summary>
internal static class PyCompat
{
    /// <summary>
    /// repr(float): fixed notation for 1e-4 &lt;= |x| &lt; 1e16, else
    /// scientific with a sign and a two-digit exponent. Unlike JS, C#
    /// preserves the int/float distinction, so integer-valued doubles
    /// render "2.0" exactly like Python floats.
    /// </summary>
    public static string PyFloat(double value)
    {
        // shortest round-trip digits, culture-invariant (never "2,5")
        string s = value.ToString("R", CultureInfo.InvariantCulture);
        bool neg = s.StartsWith('-');
        if (neg) s = s[1..];

        string digits;
        int exp; // exponent of the first significant digit
        int e = s.IndexOfAny(['E', 'e']);
        if (e >= 0)
        {
            string mant = s[..e];
            exp = int.Parse(s[(e + 1)..], CultureInfo.InvariantCulture);
            int dot = mant.IndexOf('.');
            digits = dot < 0 ? mant : mant.Remove(dot, 1);
            // mantissa may be like "1.5" (normalized): exponent already
            // refers to the leading digit
        }
        else
        {
            int dot = s.IndexOf('.');
            string all = dot < 0 ? s : s.Remove(dot, 1);
            int intLen = dot < 0 ? s.Length : dot;
            int firstSig = 0;
            while (firstSig < all.Length - 1 && all[firstSig] == '0') firstSig++;
            digits = all[firstSig..];
            exp = intLen - 1 - firstSig;
        }
        digits = digits.TrimEnd('0');
        if (digits.Length == 0) digits = "0";

        string body;
        if (value != 0.0 && (exp < -4 || exp >= 16))
        {
            string m = digits.Length > 1 ? digits[0] + "." + digits[1..] : digits;
            body = m + "e" + (exp < 0 ? "-" : "+")
                 + Math.Abs(exp).ToString(CultureInfo.InvariantCulture).PadLeft(2, '0');
        }
        else if (exp >= 0)
        {
            string ip = digits.Length > exp ? digits[..(exp + 1)] : digits.PadRight(exp + 1, '0');
            string fp = digits.Length > exp + 1 ? digits[(exp + 1)..] : "";
            body = ip + "." + (fp.Length > 0 ? fp : "0");
        }
        else
        {
            body = "0." + new string('0', -exp - 1) + digits;
        }
        return neg ? "-" + body : body;
    }

    /// <summary>str() for numbers: long as digits; double via PyFloat with
    /// nan/inf like Python.</summary>
    public static string PyNumber(object value) => value switch
    {
        long l => l.ToString(CultureInfo.InvariantCulture),
        double d when double.IsNaN(d) => "nan",
        double d when double.IsPositiveInfinity(d) => "inf",
        double d when double.IsNegativeInfinity(d) => "-inf",
        double d => PyFloat(d),
        int i => i.ToString(CultureInfo.InvariantCulture),
        _ => Convert.ToString(value, CultureInfo.InvariantCulture) ?? "",
    };

    public static string PyTypeName(object? value) => value switch
    {
        null => "NoneType",
        bool => "bool",
        long or int => "int",
        double => "float",
        string => "str",
        System.Collections.IDictionary => "dict",
        System.Collections.IEnumerable => "list",
        _ => value.GetType().Name,
    };

    /// <summary>repr(str): quote choice + escapes for control characters.
    /// Exotic non-printables beyond Latin-1 stay literal (ADR-002 margin);
    /// ASCII and common text are exact.</summary>
    private static string PyReprStr(string s)
    {
        char q = s.Contains('\'') && !s.Contains('"') ? '"' : '\'';
        var sb = new StringBuilder().Append(q);
        foreach (char ch in s)
        {
            if (ch == '\\' || ch == q) sb.Append('\\').Append(ch);
            else if (ch == '\n') sb.Append("\\n");
            else if (ch == '\r') sb.Append("\\r");
            else if (ch == '\t') sb.Append("\\t");
            else if (ch < 0x20 || (ch >= 0x7f && ch <= 0xa0) || ch == 0xad)
                sb.Append("\\x").Append(((int)ch).ToString("x2", CultureInfo.InvariantCulture));
            else sb.Append(ch);
        }
        return sb.Append(q).ToString();
    }

    /// <summary>repr(): containers render Python-style ({'k': 'v'}, ['a', 1]).</summary>
    public static string PyRepr(object? value) => value switch
    {
        null => "None",
        bool b => b ? "True" : "False",
        long or int or double => PyNumber(value),
        string s => PyReprStr(s),
        System.Collections.IDictionary d =>
            "{" + string.Join(", ", d.Keys.Cast<object>().Select(k =>
                PyReprStr((string)k) + ": " + PyRepr(d[k]))) + "}",
        System.Collections.IEnumerable seq =>
            "[" + string.Join(", ", seq.Cast<object?>().Select(PyRepr)) + "]",
        _ => Convert.ToString(value, CultureInfo.InvariantCulture) ?? "",
    };

    /// <summary>str(): what Python's str(r.get(f, "")) produces for
    /// JSON-safe values — None -> "None", True -> "True", containers via repr.</summary>
    public static string PyStr(object? value) =>
        value is string s ? s : PyRepr(value);

    /// <summary>
    /// round(x, nd) with CPython semantics: correctly rounded on the
    /// double's EXACT value, ties to even. G17 formatting exposes the true
    /// digits (2.675 is really 2.67499...98 and rounds DOWN); exact decimal
    /// arithmetic then rounds half-to-even. -0 normalizes to 0 (margin).
    /// </summary>
    public static double PyRound(double x, int nd)
    {
        if (double.IsNaN(x) || double.IsInfinity(x)) return x;
        // doubles at |x| >= 2^53 are all integers, so rounding at nd >= 0
        // is EXACTLY a no-op; below that, fractions exist and must round
        // (the [1e15, 2^53) band has spacing down to 0.125)
        if (Math.Abs(x) >= 9007199254740992.0) return x;
        // Exact-tie detection: the only doubles whose decimal expansion ends
        // in ...5 at digit nd+1 are k/2^(nd+1) with k odd (power-of-two
        // scaling is exact in floating point). NOTE: G17/R give SHORTEST
        // round-trip digits on modern .NET, so they cannot be trusted for
        // the exact value — but "F" formatting correctly rounds from the
        // true binary value (2.675 really is 2.67499...98 and yields "2.67").
        double scaled2 = x * Math.Pow(2, nd + 1);
        if (scaled2 == Math.Floor(scaled2) && Math.Abs(scaled2 % 2) == 1)
        {
            // exact tie: F(nd+1) renders the exact digits (<= nd+1 decimals)
            string s = x.ToString("F" + (nd + 1), CultureInfo.InvariantCulture);
            string trunc = s[..^1]; // drop the trailing "5"
            char lastDigit = '0';
            for (int i = trunc.Length - 1; i >= 0; i--)
                if (char.IsAsciiDigit(trunc[i])) { lastDigit = trunc[i]; break; }
            string chosen = (lastDigit - '0') % 2 == 0 ? trunc : BumpLastDigit(trunc);
            double tv = double.Parse(chosen, NumberStyles.Float, CultureInfo.InvariantCulture);
            return tv == 0 ? 0 : tv;
        }
        double v = double.Parse(x.ToString("F" + nd, CultureInfo.InvariantCulture),
                                NumberStyles.Float, CultureInfo.InvariantCulture);
        return v == 0 ? 0 : v;
    }

    private static string BumpLastDigit(string s)
    {
        bool neg = s.StartsWith('-');
        char[] chars = (neg ? s[1..] : s).ToCharArray();
        int carry = 1;
        for (int i = chars.Length - 1; i >= 0 && carry > 0; i--)
        {
            if (chars[i] == '.') continue;
            int d = chars[i] - '0' + carry;
            chars[i] = (char)('0' + d % 10);
            carry = d >= 10 ? 1 : 0;
        }
        string body = new(chars);
        if (carry > 0) body = "1" + body;
        return (neg ? "-" : "") + body;
    }

    /// <summary>Python string order: by code point. C# strings are UTF-16
    /// (CompareOrdinal sorts astral chars below U+E000..U+FFFF — same
    /// hazard the TS port fixed).</summary>
    /// <summary>True when a VALID surrogate pair starts at i — a lone high
    /// surrogate advances one unit like Python's per-code-point strings.</summary>
    private static bool IsPairAt(string s, int i) =>
        char.IsHighSurrogate(s[i]) && i + 1 < s.Length && char.IsLowSurrogate(s[i + 1]);

    private static int CodePointAt(string s, int i) =>
        IsPairAt(s, i) ? char.ConvertToUtf32(s, i) : s[i];

    public static int CompareCodePoints(string a, string b)
    {
        int i = 0, j = 0;
        while (i < a.Length && j < b.Length)
        {
            int ca = CodePointAt(a, i);
            int cb = CodePointAt(b, j);
            if (ca != cb) return ca < cb ? -1 : 1;
            i += IsPairAt(a, i) ? 2 : 1;
            j += IsPairAt(b, j) ? 2 : 1;
        }
        if (i < a.Length) return 1;
        if (j < b.Length) return -1;
        return 0;
    }

    /// <summary>Python comparison for sort keys: numbers/bools
    /// inter-compare, strings by code point, anything else raises like
    /// CPython (lists are an ADR-002 margin: Python compares element-wise,
    /// we raise).</summary>
    public static int PyCompare(object? a, object? b)
    {
        bool an = a is long or int or double or bool;
        bool bn = b is long or int or double or bool;
        if (an && bn) return CompareNumbers(a!, b!);
        if (a is string sa && b is string sb) return CompareCodePoints(sa, sb);
        throw new ArgumentException(
            $"'<' not supported between instances of '{PyTypeName(b)}' and '{PyTypeName(a)}'");
    }

    /// <summary>Python numeric comparison is EXACT — longs beyond 2^53 must
    /// not collapse through double conversion (64-bit ids are in-envelope).</summary>
    private static int CompareNumbers(object a, object b)
    {
        if (a is not double && b is not double)
        {
            long x = ToLong(a), y = ToLong(b);
            return x.CompareTo(y);
        }
        if (a is double da && b is double db)
            return da < db ? -1 : da > db ? 1 : 0;
        // one long, one double: compare exactly via floor decomposition
        return a is double d ? -CompareLongDouble(ToLong(b), d) : CompareLongDouble(ToLong(a), (double)b);
    }

    private static int CompareLongDouble(long l, double d)
    {
        if (double.IsNaN(d)) return 0;               // Python comparisons all False
        if (d >= 9223372036854775808.0) return -1;   // d >= 2^63 > long.MaxValue
        if (d < -9223372036854775808.0) return 1;    // d < long.MinValue
        double floor = Math.Floor(d);                // integral doubles here are exact
        long dl = (long)floor;                       // in [-2^63, 2^63): exact cast
        if (l != dl) return l < dl ? -1 : 1;
        return d > floor ? -1 : 0;                   // l == floor(d): fractional d is larger
    }

    private static long ToLong(object v) => v switch
    {
        bool b => b ? 1L : 0L,
        long l => l,
        int i => i,
        _ => throw new ArgumentException($"not an integer: {v}"),
    };

    /// <summary>Membership key with Python hash/eq semantics:
    /// True == 1 == 1.0, None its own class; containers raise (unhashable).</summary>
    public static string PyEqKey(object? value) => value switch
    {
        null => "None",
        bool b => "num:" + (b ? "1" : "0"),
        // a long that round-trips through double shares its key with the
        // equal double (Python 1 == 1.0); one that does not is exact and
        // can never equal any double, so it keys by its own digits
        long l => LongKey(l),
        int i => "num:" + ((double)i).ToString("R", CultureInfo.InvariantCulture),
        // -0.0 == 0.0 in Python: normalize the sign of zero before keying
        double d => "num:" + (d == 0 ? 0.0 : d).ToString("R", CultureInfo.InvariantCulture),
        string s => "str:" + s,
        _ => throw new ArgumentException($"unhashable type: '{PyTypeName(value)}'"),
    };

    private static string LongKey(long l)
    {
        // guard before the narrowing cast: (double)long.MaxValue is 2^63,
        // and casting that back is UB-adjacent (x64 wraps, ARM64 saturates
        // — saturation would falsely claim a round-trip)
        double d = (double)l;
        bool roundTrips = d >= -9223372036854775808.0 && d < 9223372036854775808.0
                          && (long)d == l;
        return roundTrips
            ? "num:" + d.ToString("R", CultureInfo.InvariantCulture)
            : "int:" + l.ToString(CultureInfo.InvariantCulture);
    }

    /// <summary>Map a UTF-16 index to a code-point index (Python str
    /// positions). Identity when no surrogates are present.</summary>
    public static Func<int, int> CodePointIndexer(string text)
    {
        bool hasSurrogates = text.Any(char.IsSurrogate);
        if (!hasSurrogates) return i => i;
        var map = new Dictionary<int, int>();
        int cp = 0;
        for (int i = 0; i < text.Length; cp++)
        {
            map[i] = cp;
            i += IsPairAt(text, i) ? 2 : 1;
        }
        map[text.Length] = cp;
        return i => map[i];
    }

    public static int CodePointLength(string text)
    {
        int n = 0;
        for (int i = 0; i < text.Length; i += IsPairAt(text, i) ? 2 : 1) n++;
        return n;
    }

    /// <summary>Slice by code points (Python str slicing).</summary>
    public static string CodePointSlice(string text, int count)
    {
        int i = 0, cp = 0;
        while (i < text.Length && cp < count)
        {
            i += IsPairAt(text, i) ? 2 : 1;
            cp++;
        }
        return text[..i];
    }

    // Python str.rstrip(): includes U+001C-U+001F and NEL (U+0085); does NOT
    // strip U+FEFF (not Python whitespace). Explicit escapes so no invisible
    // characters live in source.
    private static readonly char[] PyWhitespace =
    [
        '\u0009', '\u000a', '\u000b', '\u000c', '\u000d', '\u001c', '\u001d', '\u001e',
        '\u001f', '\u0020', '\u0085', '\u00a0', '\u1680', '\u2000', '\u2001', '\u2002',
        '\u2003', '\u2004', '\u2005', '\u2006', '\u2007', '\u2008', '\u2009', '\u200a',
        '\u2028', '\u2029', '\u202f', '\u205f', '\u3000',
    ];

    public static string PyRstrip(string text) => text.TrimEnd(PyWhitespace);
}
