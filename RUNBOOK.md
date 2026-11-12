# Krayon Sports — post runbook

Instructions for each scheduled run. Every run is a fresh session: read this file fully first.

Instagram account: **@krayon_sports**, published through the Windsor.ai connector
(connector `instagram`, account id `17841463737212811`).
Image host: this repo. Public URL of a slide:
`https://raw.githubusercontent.com/ronakdave31/krayon-sports-content/main/posts/<slug>/slide-<n>.jpg`

## Hard rules

- **Never publish without Ronak's explicit "yes" in this run's conversation.** No reply = no post.
- Facts only from pages you actually opened; at least 2 independent sources for the core claim.
  Rumours, unnamed-source figures and provisional dates are labelled "reported" / "expected".
- Graphics and text only: no photos of players, no broadcast footage or screenshots, no club or league logos.
- Don't repeat a story already in `posted.json` unless there is a genuinely new development.
- Stay politically neutral; no betting or fantasy-app promotion.

## 1. Set up

```bash
pip install --break-system-packages fonttools pillow >/dev/null
which rsvg-convert || (apt-get install -y librsvg2-bin >/dev/null)
```
Read `posted.json`: note the last `series` number, the last 3 sports covered, and any `pending` posts.
A `pending` post from an earlier run is stale: set its status to `expired`, never publish it.

## 2. Pick the story

Search for what happened in the last 24–48 hours (today's date first). Cover, in rotation:
cricket (India men/women, IPL/WPL business), football (ISL, India team, Premier League, Champions League),
F1 and Indian motorsport, Olympic and Indian sports (hockey, kabaddi, badminton, chess, athletics, boxing, wrestling, shooting),
and sports business (auctions, sponsorships, media rights, valuations).

Choose the story Indian fans will care most about **today**, then prefer a different sport from the
last post if two stories are close. The page's promise: *"Scores tell you who won. We tell you why."*
So pick an angle that explains **why** something happened or **what it means**, not a bare result.

## 3. Shape the post

- **Single (1 slide)** for breaking news: `hero` slide.
- **Carousel (3–6 slides)** for explainers: open with `hero`, then `stat` / `bars` / `text`, end with a question.
- Write the **concept**: one short paragraph on the creative idea behind the design (what the visual
  device is and why it suits this story). Ronak wants this with every post.
- **Caption**: hook line (first 5 words matter) · 2–4 short lines of explanation · one question to drive
  comments · 4–6 hashtags, always `#KrayonSports`. Under 2,000 characters. Credit sources in plain words
  when a figure is reported.

Slug: `YYYY-MM-DD-am|pm-short-topic`. Series: last number + 1, format `NN / BREAKING`, `NN / THE BREAKDOWN`,
`NN / THE GRID`, etc. Sport colour keys: `cricket` blue, `football` green, `f1`/`motorsport` red,
`indian` orange, `business` gold.

Write `posts/<slug>/spec.json` (format documented at the top of `render.py`), then:

```bash
python3 render.py posts/<slug>/spec.json
```
Open `posts/<slug>/preview.jpg` and every slide with the Read tool. Fix any WARNING or anything
cramped, overlapping or cut off by shortening text, and re-render.

## 4. Host the images

```bash
git add posts/<slug> && git commit -m "Post: <slug>" && git push origin main
curl -sI https://raw.githubusercontent.com/ronakdave31/krayon-sports-content/main/posts/<slug>/slide-1.jpg | head -1   # expect 200
```

## 5. Ask for approval

Add the post to `posted.json` with `"status": "pending"`, commit and push.
Send Ronak (SendUserMessage + SendUserFile with the slide JPEGs, then a push notification if available):
- the slides
- the concept
- the caption exactly as it will be posted
- the sources
- "Reply **yes** to publish to @krayon_sports, or tell me what to change."

Then wait. If he asks for changes, edit, re-render, re-push and show the new version before asking again.

## 6. Publish (only after "yes")

Windsor.ai `execute_action`, connector `instagram`, account `17841463737212811`:
- 1 slide → action `create_image_post`, params `{"image_url": <url>, "caption": <caption>}`
- 2–10 slides → action `create_carousel_post`, params `{"image_urls": [<urls in order>], "caption": <caption>}`

Then set the entry's `status` to `published`, store the returned media id and time, commit and push,
and tell Ronak it's live.

## posted.json entry

```json
{"slug": "...", "series": 5, "sport": "cricket", "headline": "...", "format": "single|carousel",
 "status": "pending|published|expired|rejected", "created": "ISO time", "published": "ISO time or null",
 "media_id": null, "sources": ["..."]}
```
