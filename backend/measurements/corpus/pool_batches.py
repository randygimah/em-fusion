"""Pool two batches and recompute the statistics. Usage: pooled.py 'r tp n fp n' ..."""
import sys
from math import comb

def fisher(a, b, c, d):
    n, row1, col1 = a+b+c+d, a+b, a+c
    f = lambda x: comb(row1, x) * comb(n-row1, col1-x) / comb(n, col1)
    obs = f(a)
    return sum(f(x) for x in range(max(0, col1-(n-row1)), min(row1, col1)+1)
               if f(x) <= obs*(1+1e-9))

def wilson(k, n, z=1.96):
    if not n: return (0.0, 1.0)
    ph, d = k/n, 1 + z*z/n
    c = (ph + z*z/(2*n))/d
    h = z*((ph*(1-ph)/n + z*z/(4*n*n))**0.5)/d
    return max(0, c-h), min(1, c+h)

rows = [tuple(map(float, a.split())) for a in sys.argv[1:]]
print(f"{'radius':>7} {'staged':>10} {'control':>10} {'recall':>17} {'false alarm':>17} "
      f"{'J':>6} {'p':>8}")
print("-" * 82)
for r, tp, ns, fp, nc in rows:
    tp, ns, fp, nc = int(tp), int(ns), int(fp), int(nc)
    rl, rh = wilson(tp, ns); fl, fh = wilson(fp, nc)
    print(f"{r:>7.0f} {tp:>5}/{ns:<4} {fp:>5}/{nc:<4} "
          f"{tp/ns:>6.0%} [{rl:.0%}-{rh:.0%}]".ljust(56)
          + f"{fp/nc:>5.0%} [{fl:.0%}-{fh:.0%}]".ljust(0)
          + f"  {tp/ns - fp/nc:>+5.2f} {fisher(tp, ns-tp, fp, nc-fp):>8.3f}")
