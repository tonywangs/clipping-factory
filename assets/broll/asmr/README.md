# ASMR source clips

Drop AI-generated "impossible material" clips here, one folder per collection:

```
assets/broll/asmr/glass-fruit/mango_slice.mp4
assets/broll/asmr/glass-fruit/kiwi_cut.mp4
assets/broll/asmr/frozen-honey/...
```

Generate them with Sora / Veo / Runway ("macro shot, knife slicing a fruit made of
colored glass, crisp cutting sound") and export as mp4/mov. Then:

```bash
python -m clipfactory.create asmr --collection glass-fruit
```
