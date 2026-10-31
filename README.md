# Living Portraits

Bring an old family photo to the ofrenda. Living Portraits mends its creases, returns its colour
and gives it depth, using only open-source models on a server you control.

**The face is never moved, re-posed or given words.** The photo comes back to life through
light, colour and depth instead.

Built for the DEV Hacktoberfest Open-Source AI Challenge, Week 4: *Ghost in the Machine*.

![The Return](docs/media/unnamed-1910-return.gif)

## The Return

When a photo is placed on the altar, the page plays one short sequence on a WebGL canvas:

1. The photo appears as it is today: faded, creased, black and white.
2. A line of candlelight sweeps down and mends it.
3. Colour blooms outward from the person's face.
4. The portrait settles into depth. It shifts gently with your cursor or as you tilt your phone,
   and candlelight flickers brighter on what is nearer.

The page can record the Return as a video to keep or share.

## The pipeline

| Step | Model | Licence |
|---|---|---|
| Mend | [GFPGAN v1.4](https://github.com/TencentARC/GFPGAN) (+ [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) on GPU) | Apache-2.0 / BSD-3 |
| Colour | [DDColor](https://github.com/piddnad/DDColor) (predicts colour only; light and detail come from the original) | Apache-2.0 |
| Depth | [Depth Anything V2 Small](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf) | Apache-2.0 |
| Check | [facexlib](https://github.com/xinntao/facexlib) RetinaFace + ArcFace: compares the face before and after | MIT |

The restored face is blended with the original (`weight=0.6`) so the person keeps looking like
themselves, and the ArcFace check measures it.

## Results

Eleven public-domain portraits from Wikimedia Commons (`samples/` and `samples/unnamed/`):

| | Laptop (RTX 3050, 4 GB) | DigitalOcean CPU Droplet (4 vCPU, 8 GB) |
|---|---|---|
| Time per photo (median) | 5-6 s | 11.7 s |
| Identity, ArcFace cosine (median) | 0.94 | 0.95 (one photo) |

10 of 11 portraits scored 0.88 or higher. The lowest (0.74) is Rabindranath Tagore's side profile:
face models find profiles harder. On the Droplet ($0.125 an hour), one photo costs about $0.0004 of compute.

## Run it

**DigitalOcean Droplet** (Ubuntu 24.04, GPU optional):

```bash
git clone <this repo> /opt/lp/app
sudo bash /opt/lp/app/server/setup.sh
sudo cp /opt/lp/app/server/living-portraits.service /etc/systemd/system/
sudo systemctl enable --now living-portraits     # serves on port 80
```

**Windows laptop with an NVIDIA GPU:**

```powershell
powershell -ExecutionPolicy Bypass -File server\setup_windows.ps1
cd server; ..\.local\venv\Scripts\uvicorn app:app --port 8000
```

**Evaluate a folder of photos, and render the Return as a GIF:**

```bash
python server/evaluate.py samples/ --out results/
python server/render_return.py results/Kasturba_Gandhi --face 0.54,0.37 --out docs/media/kasturba-return
```

## Licences and credits

Code in this repo: MIT. Model licences belong to their authors (table above).

All sample photos come from Wikimedia Commons and are public domain or CC0. The portraits in
`samples/unnamed/` are of people whose names were not recorded:

| File | Source | Licence |
|---|---|---|
| unnamed_1.jpg | [A milk-woman in India (late 19th or early 20th century)](https://commons.wikimedia.org/wiki/File%3AA_milk-woman_in_India_%28late_19th_or_early_20th_century%29.jpg) | Public domain |
| unnamed_2.jpg | [Portrait of an unidentified Indian woman in the 1860s](https://commons.wikimedia.org/wiki/File%3APortrait_of_an_unidentified_Indian_woman_in_the_1860s.jpg) | Public domain |
| unnamed_3.jpg | [Studio portrait of an Indian woman in sari and various ornaments in the 1880s](https://commons.wikimedia.org/wiki/File%3AStudio_portrait_of_an_Indian_woman_in_sari_and_various_ornaments_in_the_1880s.jpg) | Public domain |
| unnamed_4.jpg | [Studioportret van een Indiase vrouw met sieraden en een kan, RP-F-F80348](https://commons.wikimedia.org/wiki/File%3AStudioportret_van_een_Indiase_vrouw_met_sieraden_en_een_kan%2C_RP-F-F80348.jpg) (Rijksmuseum) | CC0 |
| unnamed_5.jpg | [Studioportret van twee Indiase vrouwen, RP-F-F80378-A](https://commons.wikimedia.org/wiki/File%3AStudioportret_van_twee_Indiase_vrouwen_in_traditionele_kleding_uit_een_berggebied_Aboriginal_Tribes_Zeilgherry_Hills_%28titel_op_object%29%2C_RP-F-F80378-A.jpg) (Rijksmuseum) | CC0 |
| unnamed_6.jpg | [Indian Christian, India, ca. 1910 (IMP-CSCNWW33-OS14-35)](https://commons.wikimedia.org/wiki/File%3AIndian_Christian%2C_India%2C_ca._1910_%28IMP-CSCNWW33-OS14-35%29.jpg) | Public domain |

The other samples (Kasturba Gandhi, Srinivasa Ramanujan, Rabindranath Tagore, Marie Curie,
Frederick Douglass) are public-domain portraits from Wikimedia Commons.
