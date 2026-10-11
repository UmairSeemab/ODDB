ODDB v1 image-led intro v0.5.5

Files:
  public/assets/intro.css
  public/assets/intro.js
  public/assets/oddb-eye-front.svg
  public/assets/oddb-eye-anatomy.svg
  public/assets/oddb-eye-diseases.svg

The SVG files preserve the supplied artwork exactly by embedding the corresponding PNG
inside a responsive SVG container. This is raster-backed SVG, not path-traced vector art.
That choice preserves the detailed gradients, anatomy and typography from the supplied images.

Install:
  cd ~/Documents/DBMS/codes4ODDB/ODDB-RetNet-harmonization-2026-09-28/ODDB_v1_webapp_v0.4
  python3 install_oddb_image_intro_v0.5.5.py

Requires the v0.5.4 intro wrapper already present in public/index.php.
Replay:
  http://127.0.0.1:8081/index.php?intro=1
