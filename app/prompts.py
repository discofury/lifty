"""Coaching prompts for each supported lift.

The system prompt sets up the coach persona and the output format the
phone UI expects. Each lift entry contributes the technical checklist the
model should assess against.
"""

SYSTEM_PROMPT = """\
You are an experienced Olympic weightlifting coach reviewing video of a lifter \
between sets at the gym. You are shown a sequence of still frames extracted from \
a single set, in chronological order with timestamps.

Your job is to give feedback the lifter can act on IMMEDIATELY, before their next \
set, which starts in a couple of minutes.

How to work:
- Reconstruct the movement from the frame sequence: identify the phases of the \
lift and which frames show each phase.
- Judge positions and bar path against the technical model for the declared \
exercise. The lifter tells you which exercise and variation they intended - \
assess against that standard.
- If the set contains multiple reps, comment on consistency across reps and on \
fatigue-related breakdown.
- Be honest and specific. Refer to visible evidence ("in the frame at ~1.2s your \
shoulders are behind the bar") rather than generic advice.
- If the camera angle, framing, or frame coverage genuinely prevents you from \
assessing something important, say so briefly and tell the lifter how to film \
the next set (angle, distance, portrait/landscape). Do not pad the review with \
caveats - one short note is enough.

Output format (markdown, in this exact order):

## Next set: one cue
A single short, actionable coaching cue - the highest-leverage fix. One or two \
sentences max, phrased the way a coach would say it on the platform.

## What's working
2-4 bullet points on what the lifter is doing well. Be specific.

## What to fix
The main faults you observed, most important first, each with: what you saw \
(with frame/time reference), why it matters, and how to fix it. Maximum 3 - \
do not list every minor imperfection.

## Watch for next time
Optional, one or two lines: anything to monitor as the load goes up, or a note \
on filming angle if needed.

Keep the whole response tight - the lifter is resting between sets, not reading \
an essay.\
"""

# Per-lift technical standards appended to the user message.
LIFTS: dict[str, dict[str, str]] = {
    "clean_pull_shin": {
        "label": "Clean pull to below-knee (shin)",
        "standard": """\
Exercise: CLEAN PULL TO BELOW THE KNEE (first pull only - bar travels from the \
floor to mid/upper shin, below the knee, then is returned).

Assess against this technical model:
- Setup: bar over the mid-foot, contact with or very close to the shins; \
shoulders directly over or slightly ahead of the bar; hips above knees, \
shoulders above hips; back set flat/extended, lats engaged; arms straight and \
relaxed, hook grip.
- Separation: bar breaks the floor by pushing the legs into the platform, NOT by \
raising the hips first. Hips and shoulders rise at the same rate - the back \
angle set at the start should be preserved throughout this pull height.
- Knees move back/out of the way as the bar rises; bar stays close, drifting \
back toward the lifter, not swinging out.
- Weight balanced over the whole foot / mid-foot - not rocking onto the toes.
- Arms stay long and loose - no bending at this height.
- Common faults to check: hips shooting up early (back angle steepening), bar \
looping forward around the knees, shoulders drifting behind the bar too early, \
rounding of the upper or lower back, yanking the bar off the floor.\
""",
    },
    "clean_pull_knee": {
        "label": "Clean pull to knee",
        "standard": """\
Exercise: CLEAN PULL TO THE KNEE (bar travels from the floor to knee height, \
then is returned).

Assess against this technical model:
- Everything from the first pull applies: back angle preserved from the floor, \
knees moving back, bar staying close, weight mid-foot, straight arms.
- At the knee: shoulders should still be over or slightly in front of the bar; \
shins approaching vertical; hamstrings loaded (visible hip hinge maintained).
- The position at the knee is the checkpoint - hold/pause quality if the lifter \
pauses there.
- Common faults to check: shoulders behind the bar at the knee (premature \
opening), bar drifting away from the legs, knees failing to move back so the \
bar has to loop around them, back angle changing (hips rising faster than \
shoulders), heels lifting.\
""",
    },
    "clean_pull_thigh": {
        "label": "Clean pull to mid-thigh (power position)",
        "standard": """\
Exercise: CLEAN PULL TO MID-THIGH / POWER POSITION (bar travels from the floor \
past the knee to mid-thigh, then is returned).

Assess against this technical model:
- First pull and knee position standards apply on the way up.
- Past the knee the torso becomes more upright as the bar and knees move toward \
each other (the "scoop"/double-knee-bend): knees re-bend slightly under the \
bar, hips come to the bar, bar in contact with or brushing the thigh.
- At mid-thigh: nearly vertical torso, shoulders over the bar or just in front, \
weight still over the whole foot (not yet on the toes), arms still straight, \
bar close.
- Common faults to check: bar away from the thigh (gap = forward swing later), \
shoulders leaning back too early, weight rushing to the toes early, arms \
starting to pull, hips stopping away from the bar, no re-bend of the knees \
(pulling around straight knees).\
""",
    },
    "clean_pull_full": {
        "label": "Full clean pull (full extension)",
        "standard": """\
Exercise: FULL CLEAN PULL (floor to complete extension with aggressive leg \
drive and shrug - no pull-under, no turnover).

Assess against this technical model:
- All prior checkpoints apply: first pull back angle, knee position, scoop into \
the power position, bar close and brushing the thigh.
- Finish: violent, complete extension of hips and knees; body tall; trapezius \
shrug at the top; heels may leave the floor at the very end of extension, but \
the lifter should not jump forward or swing the bar.
- Bar path: close to vertical, bar staying over the base; contact at the hip/\
upper thigh should send the bar UP, not out.
- Arms: straight through extension - the shrug finishes the pull; elbows only \
break, if at all, after full extension.
- Timing: extension should be fastest at the top - look for continuous \
acceleration, not one-speed grinding.
- Common faults to check: incomplete extension (cutting the finish short), \
hips banging the bar forward, early arm bend, weight on toes too early, \
leaning back excessively instead of finishing tall, slow/soft finish, bar \
crashing back down out of control.\
""",
    },
    "front_squat": {
        "label": "Front squat",
        "standard": """\
Exercise: FRONT SQUAT.

Assess against this technical model:
- Rack position: bar sitting on the front deltoids/shoulders, fingertips under \
the bar, ELBOWS HIGH (upper arms near parallel to the floor) and held up \
throughout the rep, not just at the start.
- Torso: as upright as possible for the lifter's proportions; chest up; upper \
back extended. Watch the elbows/chest dropping in the hole and on the drive up.
- Descent: controlled; knees track over/outside the toes; hips sit between the \
heels rather than shooting back.
- Depth: below parallel - hip crease below top of the knee - unless mobility \
visibly prevents it.
- Bottom: no butt-wink/lumbar tucking under, no bouncing that collapses the \
torso, heels flat on the floor.
- Ascent: elbows and chest lead up; hips and shoulders rise together - watch for \
the hips rising first and turning it into a good-morning; knees not caving in \
(valgus), especially out of the hole and under fatigue.
- Common faults to check: elbows dropping, upper back rounding, weight shifting \
to the toes/heels lifting, knee valgus, cutting depth, losing brace at the \
bottom.\
""",
    },
    "rdl": {
        "label": "Romanian deadlift",
        "standard": """\
Exercise: ROMANIAN DEADLIFT (RDL) - hip hinge from the top, bar lowered along \
the legs to roughly mid-shin, then stood back up. Not a stiff-leg deadlift, \
not a conventional deadlift from the floor.

Assess against this technical model:
- Start (top): standing tall, bar at the hips, shoulders back, lats engaged \
(bar pulled into the body).
- Descent: movement initiated by pushing the HIPS BACK, not by bending the \
knees or dropping the chest; knees soften slightly and then hold that angle; \
bar slides down the thighs staying in contact or within an inch of the legs.
- Spine: neutral throughout - no lumbar rounding at the bottom, no excessive \
hyperextension; neck roughly in line with the torso.
- Depth: to where the hamstrings reach their loaded stretch with a neutral \
spine - typically just below the knee to mid-shin. Depth beyond hamstring \
range that comes from spinal flexion is a fault, not extra range.
- Shins near vertical throughout; weight over mid-foot/heels, toes staying down.
- Ascent: hips drive forward, bar stays close, lockout by squeezing the glutes \
to stand tall - no leaning back/hyperextending at the top.
- Common faults to check: bar drifting away from the legs, knees re-bending on \
the way down (turning it into a deadlift), lower back rounding at end range, \
hips rising without the chest (back-lift), jerky tempo, losing lat tension so \
the bar swings.\
""",
    },
}
