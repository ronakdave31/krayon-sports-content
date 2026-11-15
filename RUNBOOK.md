# Krayon Sports — post runbook

Instructions for each scheduled run. Every run is a fresh session: read this file fully first.

Instagram account: **@krayon_sports**, published through the Windsor.ai connector
(connector `instagram`, account id `17841463737212811`).
Image host: this repo. Public URL of a slide:
`https://raw.githubusercontent.com/ronakdave31/krayon-sports-content/<commit-sha>/posts/<slug>/slide-<n>.jpg`
(always use the commit SHA from `git rev-parse HEAD` after pushing, never `main`: `main` links are cached for minutes and can serve an older version of a re-rendered slide)

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
SHA=$(git rev-parse HEAD)
curl -sI https://raw.githubusercontent.com/ronakdave31/krayon-sports-content/$SHA/posts/<slug>/slide-1.jpg | head -1   # expect 200
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

## Photo posts (photo slot)

Use a `photo` slide when the story is about one person or one big moment (a comeback, a record, a final).
It is a full-bleed photo with the Krayon gradient, headline and logo on top. Spec fields:
`{"type": "photo", "kicker": "...", "grey": "...", "white": "...", "sub": "...", "image": "<optional>"}`

Rules:
- **Never add a photo or cutout of a real person yourself**, from any source. Leave `image` out and the
  renderer draws a placeholder; Ronak adds the photo or cutout himself.
- `image` may only point to a generic picture with no identifiable real people (stadium, ball, pitch, car,
  crowd from far away) that Ronak has put in this repo's `photos/` folder.
- Rendering a photo slide also writes `slide-N-overlay.png`: a transparent layer (gradient, text, logo).

In the preview, send Ronak both `slide-N.jpg` (placeholder version) and `slide-N-overlay.png`, and say:
"This one is built for a photo. Place your photo or cutout under the overlay (1080 x 1350), then attach the
finished image here and reply yes. Or reply **graphic** and I'll switch it to the text-only design."

- If he attaches a finished image and says yes: convert it to a 1080x1350 JPEG (crop to 4:5 if needed),
  save it as `slide-N.jpg` in the post folder, commit, push and publish that file.
- If he replies **graphic**: change the slide to `hero`, re-render, show it again and wait for yes.
- Never publish the placeholder version.

## Reel version (every post)

After the post renders, make its Reel from the same spec:
```bash
python3 render_kinetic.py posts/<slug>/spec.json   # writes reel.mp4 + reel-cover.jpg
```
The reel is the KINETIC format: visual news with motion graphics, 1080x1920. A 1 s sport-name hook, then
each slide is a scene where headlines punch in word by word, numbers count up, bars grow and a sport visual
(pitch, track, rings) draws itself behind the text; whip cuts on the beat, a progress bar and a news ticker;
it ends on the Krayon Sports end card. The soundtrack is an original beat synthesised by the script
(never add licensed or trending music). No viewer prompts or polls in reels: visual news only.
(render_reel.py is the older, calmer format; use it only if Ronak asks for it.)
Check it: pull 4-6 frames with ffmpeg (`-ss <t> -frames:v 1`) and look at them; ffprobe must show
h264 + aac, 1080x1920, 30 fps, 5-90 s. Commit reel.mp4 and reel-cover.jpg with the post.

Include the reel in the preview (send reel.mp4 and reel-cover.jpg too) and ask:
"Reply **yes** to publish both the post and the reel, **post only**, or **reel only**."

Publishing the reel (same caption as the post), Windsor.ai `execute_action`, connector `instagram`,
account `17841463737212811`, action `create_video_post`, params:
`{"video_url": <commit-SHA raw URL of reel.mp4>, "cover_url": <commit-SHA raw URL of reel-cover.jpg>,
"caption": <caption>, "share_to_feed": true}`
(Ronak wants reels to appear as posts too: share_to_feed true puts the reel in the feed and on the profile grid
as well as in the Reels tab.)
If Instagram rejects the raw.githubusercontent.com video link, retry once with the jsDelivr link
`https://cdn.jsdelivr.net/gh/ronakdave31/krayon-sports-content@<commit-sha>/posts/<slug>/reel.mp4`
(and the same jsDelivr form for the cover). Log the reel's media id in posted.json as `reel_media_id`.
For photo posts, the reel uses the text layout (no photo), so it can go out even if the post waits for a photo.

## YouTube package (every reel)

The same reel.mp4 is also posted to YouTube Shorts by Ronak himself (Windsor.ai can't upload to YouTube).
Make it ready to upload:
```bash
python3 render_thumbs.py posts/<slug>/spec.json    # writes yt-thumbnail.jpg (1280x720)
```
Optional spec field `"thumb": {"title": "...", "sub": "...", "ghost": "..."}` sharpens the thumbnail when the
hero line isn't the best hook (keep the title under ~8 words). Look at the thumbnail before sending it.

Write `posts/<slug>/youtube.md` with:
- **Title**: under 100 characters, the search words first (teams, players, tournament), ending in `#Shorts`
- **Description**: 3 short paragraphs (what happened, why it matters, what's next), then
  "Krayon Sports explains the stories, stats and money behind the game." and "Instagram: @krayon_sports",
  then 3-5 hashtags including #Shorts
- **Tags**: 6-10 comma-separated search phrases
Same writing rules as captions: no comma before "and", no long dashes, facts only from the sources.

Send youtube.md's text and yt-thumbnail.jpg with the preview, under a "For YouTube" heading, and remind him:
for a Short, the cover is picked in the YouTube app; yt-thumbnail.jpg is for uploading it as a regular video.

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
