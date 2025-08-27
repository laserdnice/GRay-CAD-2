# GRay-CAD 2

Release Version 0.1
=======
GRayCad is a powerful tool to simulate optical systems. It is based on the ABCD matrix formalism for gaussian beams.
You can simulate optical systems with (thick) lenses and mirrors but also use a own ABCD matrix.

Build in functions like the modematcher can optimize your systems. It matches a arbitary incident beam to a output beam of your choise. The algorithm used for this is the "Trust Region Reflective algorithm". After optimization you can choose one or more of the caculated setups.

The function build resonator is based on our recent paper (https://doi.org/10.1063/5.0253513). Here we use a "Genetic Algorithm" to calculate resonators in different geometries. Implemented designs are "Bow-Tie", "Fabry-Perot", "Rectangle" and "Triangle".

Installation guide:
1. download repository
2. create venv: python3 -m venv venv
3. activate venv: source bin/venv/activate
4. install requirements.txt: pip install -r requirements.txt
5. run: python3 graycad_start.py