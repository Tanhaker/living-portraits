---
title: "[[My great-grandmother's only photo was fading. I gave it back its colour, and never touched her face.]]"
published: false
tags: devchallenge, hf26challenge, opensource, ai
---

*This is a submission for the [Hacktoberfest Open-Source AI Challenge Week 4: Ghost in the Machine](https://dev.to/challenges/hacktoberfest-week4-2026-10-26)*

<!-- HOOK: replace with your own family's real scene, 3-5 short sentences. -->
[[There is one photo of my great-grandmother. It lives in a steel almirah at my grandparents' house, folded down the middle, the crease running straight through her shoulder. Nobody alive remembers the colour of her sari.]]

[[Last night I put it on an altar I built, and watched the colour come back.]]

![The Return](https://raw.githubusercontent.com/[[your-username]]/living-portraits/main/docs/media/kasturba-return-small.gif)

## What I Built

**Living Portraits** is a digital ofrenda for old family photos. You place a photo on the altar, and it comes back in one short sequence I call *the Return*:

1. The photo appears as it is today: faded, creased, black and white.
2. A line of candlelight sweeps down and mends it.
3. Colour blooms outward from their face.
4. The portrait settles into depth. Move your cursor, or tilt your phone, and it shifts gently in 3D while candlelight flickers brighter on what is nearer to you.

You can save the Return as a video and send it to the family group.

### Why a photograph

The centre of every ofrenda is a photograph. Marigolds, candles and the food someone loved are there so that, for one night, the dead can find their way home. The photo is how we recognise them when they arrive.

Many families, mine included, have only one or two photos of the people who came before us, and those photos are fading. I wanted to bring that one object back.

### The line I would not cross

My first version animated the faces: a blink, a smile, a turn of the head. I showed it to [[my sister / a friend]] and [[their reaction, e.g. "she said it felt like someone wearing my great-grandmother's face"]]. They were right. It was uncanny, and it put words in the mouth of someone who can't consent.

So I threw it away. In Living Portraits **the face is never moved, re-posed or given words.** The photo comes back to life through light, colour and depth. Every download is labelled *AI-restored*.

## Demo

- Live: [[http://139.59.7.49 or your .tech domain]]
- Video: [[60-second screen recording]]

<!-- Add a screenshot of the altar page here. -->

## Code

{% github [[your-username]]/living-portraits %}

## How I Built It

Four open-source models, chained on one server:

| Step | Model | What it does |
|---|---|---|
| Mend | GFPGAN v1.4 (Apache-2.0) | repairs blur and damage on the face |
| Colour | DDColor (Apache-2.0) | predicts colour only; the light and detail stay from the original photo |
| Depth | Depth Anything V2 Small (Apache-2.0) | estimates how near each part of the photo is |
| Check | facexlib RetinaFace + ArcFace (MIT) | finds the face, and checks it is still the same person |

The server (FastAPI) writes three images: the photo as it was, the restored photo, and a depth map. The page does the rest in a small WebGL shader: the mending sweep, the colour bloom centred on the detected face, the depth parallax and the candlelight.

### The hard part: keeping them themselves

Face-restoration models are trained to make faces look good, and "good" drifts toward young, symmetrical and generic. For a stranger's photo that might be fine. For your great-grandmother it's a small betrayal.

Two things keep it honest:

- I blend the restored face with the original (`weight=0.6` instead of 1.0).
- An ArcFace face-recognition model compares the face before and after, and the score is shown on every result.

DDColor's colours also ran hot (magenta suits, orange hands), so I scale the colour back by 25%. Old photos look more truthful with gentler colour.

### Running on DigitalOcean, without a GPU

Living Portraits runs on a **DigitalOcean CPU-Optimized Droplet** (4 vCPU, 8 GB) in Bangalore, as a systemd service. I originally planned to use a GPU Droplet, but once the face animation was gone, the remaining models were light enough for CPU:

| | Laptop (RTX 3050, 4 GB) | DigitalOcean CPU Droplet |
|---|---|---|
| Time per photo (median) | 6.2 s | 11.7 s |
| Identity, ArcFace cosine (median of 5) | 0.95 | 0.95 |
| Cost per photo | free | about $0.0004 |

A family could run their own copy for about $3 a day, or switch it off between uses.

### Where it struggles

- **Side profiles:** Rabindranath Tagore's profile portrait scored 0.74, the lowest. Face models are trained mostly on front-facing faces.
- **Colour is a guess.** DDColor doesn't know what colour her sari was. It suggests a plausible colour, and that's all it is.
- [[Anything you noticed on your family photos.]]

## Why Open Innovation Matters Here

Commercial apps already make old photos "come alive". To use them you upload your family's photos to a company's servers, usually on a subscription, and accept whatever the model decides to do to their faces.

- **The photos stay ours.** They go to a server I control, not to an AI company.
- **I could change what the AI does.** When face animation felt wrong, I removed it. When the colours were too loud, I turned them down. When restoration drifted from the real face, I measured it. None of that is possible with a closed API.
- **It can't be taken away.** No subscription to lapse, no app to shut down.
- **It's cheap:** about $0.0004 a photo on a small CPU server, or free on a laptop with a 4 GB GPU.

## The Moment It Landed

[[Write this yourself, in your own words: who you showed it to, what photo, what they said or did. This is the most important paragraph in the post.]]

## Prize Categories

- **Best Use of DigitalOcean:** the whole app (models, API and page) runs on a DigitalOcean CPU-Optimized Droplet, deployed with a setup script and systemd service in the repo. It shows open-source image models don't need a GPU to be useful to a family.

---

*Built with help from an AI coding assistant. Sample portraits are public domain (Wikimedia Commons). Family photos are shared with permission.*
