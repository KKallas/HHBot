# HHBot

A physical robotics game and interactive teaching environment — two Dobot MG400 arms compete to grab ESP32 tags off a shared field. Inspired by Hungry Hungry Hippos.

## Overview

HHBot is a hands-on educational platform that combines robot arm control, computer vision, and embedded systems into a competitive game. Two Dobot MG400 robot arms face each other across a play field, their working areas deliberately overlapping by roughly 50%. Scattered across the overlap zone are lightweight ESP32-powered tags, each displaying a marker worth a different number of points. Players (or autonomous agents) pick up tags and deliver them to a scoring receptacle — and the race is on.

The system is designed as a teaching tool — a **replacement for Scratch** — where students program real hardware with Claude Code instead of drag-and-drop blocks. They start by clicking on a live camera feed to command the arm, then use AI-assisted coding to optimize their pickup strategy, and finally build fully autonomous routines that read the field and act on their own.

## How It Works

### The Game Field

Each round lasts **90 seconds**. The two MG400 arms are positioned so their reachable areas overlap in the center. The shared zone holds the ESP32 tags — small (<3 g) battery-powered boards with on-screen markers. Most tags are worth **1 point**, but the dashboard highlights the **next valuable item** (worth **10 points**) on screen — it stays highlighted until someone delivers it to their receptacle, then a new one is chosen.

### Picking Up Tags

Each arm uses a vacuum pump end-effector to grab tags. Tags are delivered to a dispensing box (receptacle) where scoring is validated by weight — tags don't need to land face-up.

### The Dashboard (Manual Mode)

The player sees the Nilsson environment with a dashboard showing a **top-down camera view** of the game field. Clicking on the field sends image coordinates to a Python backend that converts them to robot-arm coordinates, moves the arm to that position, picks up the tag, and delivers it to the dispensing box.

### AI-Assisted Optimization

The control Python is exposed to the user. With agent help (Nilsson), players can modify the pickup and delivery code — optimizing path planning, grip timing, or multi-tag sequencing for faster manipulation.

### Collisions

Because the arms share roughly half their working area, **collisions are real and physical**. The MG400 has built-in collision detection — when it triggers, the robot enters alarm state (`RobotMode() == 11`) and all motion stops.

**Reset procedure** (fully remote via TCP port 29999 — no physical button required):

1. `ClearError()` — clear the collision alarm
2. `RobotMode()` — poll until it returns **5** (enabled/idle = ready to go, the "ref with three fingers up")
3. `EnableRobot()` — re-enable if the robot fully disabled during the alarm
4. `Continue()` — resume any queued motion commands

**The penalty is deliberately prohibitively expensive.** The reset sequence itself costs several seconds of the 90-second clock, and the system applies a **point deduction** on top. Players learn fast that collision avoidance isn't optional — it's the core engineering challenge. Competing for the same 10-point tag is tempting, but not if a collision wipes out your lead.

### Autonomous Mode

A separate routine runs on a regular interval: it analyzes the camera image, identifies tag positions and classes, and creates movement events automatically when certain conditions are met — no clicks required.

## Hardware

| Component | Details |
|---|---|
| Robot arms | 2x [Dobot MG400](https://www.dobot-robots.com/products/desktop-four-axis/mg400.html) desktop 4-axis arms (500 g payload) |
| End-effectors | Vacuum pump grippers |
| Tag controller | [M5Stack AtomS3R Dev Kit](https://shop.m5stack.com/products/atoms3r-dev-kit?variant=45605332615425) — ESP32-S3, 0.85" IPS LCD, BMI270 IMU, 6.8 g |
| Tag battery | [M5Stack Atomic Battery Base 200 mAh](https://shop.m5stack.com/products/atomic-battery-base-200mah) — 3.7 V Li-ion, USB-C charge, 9.9 g |
| Tag total | ~16.7 g stacked, 24 × 24 × ~37 mm — well under the MG400's 500 g vacuum payload (see [docs/tag-hardware.md](docs/tag-hardware.md)) |
| Camera | Top-down overhead camera covering the game field |
| Receptacles | Dispensing boxes (one per arm) with weight-based validation |

### Tag Firmware

Each tag runs a small PlatformIO firmware on the AtomS3R. On boot it joins the local Wi-Fi and announces itself (mDNS / UDP broadcast) with its tag ID and IP. The **game master** discovers tags this way and opens a persistent connection to each one — the tag's display behaves as a thin **remote screen** the game master pushes marker images to.

This keeps game logic centralized: the game master decides which tag is the 10-point featured item and just pushes a different marker to that tag's display. The tag itself stays dumb — it renders what it's told and reports accelerometer events (handling, pickup) back over the same connection.

## Architecture

Three Nilsson instances make up the system. The **game master (Nilsson 3)** sits at the center — both robots connect directly to it, and both player machines communicate through it. Players never talk to the bots directly.

```
  Player 1                                Player 2

┌──────────────────┐                ┌──────────────────┐
│  Nilsson (1)     │                │  Nilsson (2)     │
│  Dashboard +     │                │  Dashboard +     │
│  Python backend  │                │  Python backend  │
└────────┬─────────┘                └────────┬─────────┘
         │                                   │
         └──────────┐           ┌────────────┘
                    ▼           ▼
          ┌─────────────────────────────┐
          │      Nilsson (3)            │
          │      GAME MASTER            │
          │  Camera · Score · Timer     │
          │  (90 s countdown)           │
          └──┬──────────────────────┬───┘
             │ TCP :29999           │ TCP :29999
             ▼                      ▼
       ┌───────────┐          ┌───────────┐
       │  MG400    │  shared  │  MG400    │
       │  Arm 1    │◄─overlap─▶  Arm 2    │
       └───────────┘          └───────────┘
             ▲          ▲           ▲
             └──────────┼───────────┘
                        │
               ┌────────▼─────────┐
               │   ESP32 Tags     │
               │ (markers, accel) │
               └──────────────────┘
```

The **game master** is the authoritative server: it owns the camera, runs the 90-second countdown, tracks score, decides which tag is the featured 10-point item, and relays the camera feed to both player Nilsson instances. Player code sends move commands to the game master, which forwards them to the correct arm.

### Simulator Mode

When no physical hardware is available, the game master connects to a **simulator** instead of real MG400 arms. The simulator accepts the same TCP API calls the Dobot bots do but renders the game field as drawn video and outputs an **H.264 stream** in place of a real camera feed. Player Nilsson instances don't change — they still talk to the game master the same way.

## Scoring

- **Regular tags** — 1 point each
- **Featured tag** — 10 points; the dashboard highlights the next valuable item on screen until it is collected, then a new one is selected
- **Collision penalty** — point deduction + seconds lost to the reset sequence (ClearError → re-enable → resume)
- Round duration: **90 seconds**
- Tags are delivered to the player's receptacle (dispensing box)
- Delivery is validated by weight — orientation doesn't matter
- The ESP32 accelerometer can detect handling events

## License

This project is licensed under the [MIT License](LICENSE).
