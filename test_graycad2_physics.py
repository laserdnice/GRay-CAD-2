"""
Regressionstests fuer die Physik von GRay-CAD 2.
Ausfuehren im Repo-Root: python3 test_graycad2_physics.py
Benoetigt nur numpy (kein PyQt) - importiert ausschliesslich src_physics.matrices.

Getestete Punkte:
  1. Duenne Linse / Spiegel: Grundmatrizen
  2. Gekruemmte Grenzflaeche in reduzierter Konvention (Lensmaker-Vergleich)
  3. BowTie-Resonator: Umlauf muss den Eigen-q reproduzieren ("schliessen")
  4. Grad/Radiant-Sensitivitaet des Einfallswinkels (Demonstration des GUI-Bugs)
"""
import numpy as np
import sys
sys.path.insert(0, '.')
from src_physics.matrices import Matrices

M = Matrices()
lam = 532e-9

def prop_q(q, mat):
    A, B, C, D = mat.flatten()
    return (A * q + B) / (C * q + D)

def w_reduced(q, lam):
    """Strahlradius aus reduziertem q (Konvention des Programms, n steckt in q)."""
    return np.sqrt(-lam / (np.pi * np.imag(1 / q)))

def roundtrip(seq):
    R = None
    for m in seq:
        R = m @ R if R is not None else m
    return R

# ---------------------------------------------------------------
print("Test 1: Grundmatrizen")
f = 0.1
assert np.allclose(M.lens(f), [[1, 0], [-10, 1]])
# Tangential: f_eff = R cos(theta)/2 ; Sagittal: f_eff = R/(2 cos(theta))
R_, th = 0.2, np.deg2rad(10)
assert np.isclose(M.curved_mirror_tangential(R_, th)[1, 0], -2 / (R_ * np.cos(th)))
assert np.isclose(M.curved_mirror_sagittal(R_, th)[1, 0], -2 * np.cos(th) / R_)
assert np.isclose(M.free_space(0.3, 1.5)[0, 1], 0.2)  # reduziert: B = d/n
print("  OK")

# ---------------------------------------------------------------
print("Test 2: Gekruemmte Grenzflaeche vs. Lensmaker (dicke Bikonvexlinse)")
n_g, R1, R2, t = 1.517, 0.0516, -0.0516, 0.004
inv_f_ref = (n_g - 1) * (1 / R1 - 1 / R2 + (n_g - 1) * t / (n_g * R1 * R2))
sys_m = (M.refraction_curved_interface(R2, n_g, 1.0)
         @ M.free_space(t, n_g)
         @ M.refraction_curved_interface(R1, 1.0, n_g))
f_sys = -1 / sys_m[1, 0]
assert np.isclose(f_sys, 1 / inv_f_ref, rtol=1e-10), \
    f"Grenzflaechenmatrix falsch: f={f_sys*1e3:.3f} mm, erwartet {1e3/inv_f_ref:.3f} mm"
print(f"  OK  (f = {f_sys*1e3:.3f} mm)")

# ---------------------------------------------------------------
print("Test 3: BowTie-Resonator schliesst (q reproduziert sich nach 1 Umlauf)")
nc, lc, n0 = 1.8, 0.01, 1.0
l1, l3, theta = 0.05, 0.4, np.deg2rad(8)
l2 = ((2 * l1) + lc + l3) / (2 * np.cos(2 * theta))
Rc, Rf = 0.1, 1e9

for name, mir in (("sagittal", M.curved_mirror_sagittal),
                  ("tangential", M.curved_mirror_tangential)):
    seq = [M.free_space(lc / 2, nc), M.free_space(l1, n0), mir(Rc, theta),
           M.free_space(l2, n0), mir(Rf, theta), M.free_space(l3, n0),
           mir(Rf, theta), M.free_space(l2, n0), mir(Rc, theta),
           M.free_space(l1, n0), M.free_space(lc / 2, nc)]
    Rt = roundtrip(seq)
    A, B, C, D = Rt.flatten()
    m_stab = (A + D) / 2
    assert abs(m_stab) < 1, f"{name}: Testresonator instabil, m={m_stab}"
    # Waist-Formel wie im Programm (Referenzebene = Kristallmitte, A==D dort)
    w0 = np.sqrt((abs(B) * lam / np.pi) * np.sqrt(abs(1 / (1 - m_stab**2))))
    q = 1j * np.pi * w0**2 / lam
    q0 = q
    for mat in seq:
        q = prop_q(q, mat)
    assert np.isclose(q.real, q0.real, atol=1e-9) and np.isclose(q.imag, q0.imag, rtol=1e-6), \
        f"{name}: Resonator schliesst nicht! q0={q0}, q_ende={q}"
    print(f"  OK  ({name}: w0 = {w0*1e6:.2f} um, m = {m_stab:+.3f})")

# ---------------------------------------------------------------
print("Test 4: Demonstration - Winkel in Grad statt Radiant zerstoert den Umlauf")
theta_bad = np.rad2deg(theta)  # 8.0 als "Radiant" interpretiert
seq_bad = [M.free_space(lc / 2, nc), M.free_space(l1, n0), M.curved_mirror_sagittal(Rc, theta_bad),
           M.free_space(l2, n0), M.curved_mirror_sagittal(Rf, theta_bad), M.free_space(l3, n0),
           M.curved_mirror_sagittal(Rf, theta_bad), M.free_space(l2, n0), M.curved_mirror_sagittal(Rc, theta_bad),
           M.free_space(l1, n0), M.free_space(lc / 2, nc)]
q = 1j * np.pi * (22.4e-6)**2 / lam
q0 = q
for mat in seq_bad:
    q = prop_q(q, mat)
assert not np.isclose(w_reduced(q, lam), w_reduced(q0, lam), rtol=0.01), \
    "erwartete Nicht-Schliessung blieb aus?"
print(f"  OK  (w: {w_reduced(q0,lam)*1e6:.1f} um -> {w_reduced(q,lam)*1e6:.1f} um, wie erwartet kaputt)")

print("\nAlle Tests bestanden.")
