# Task 4 -- Subject-Agnostic Q-Learning

Training used several randomly generated acyclic topic graphs rather than topic names.

## State abstraction
Each candidate is represented by mastery bucket, difficulty-gap bucket, engagement bucket, and prerequisite-ready flag.

## Abstract action
Actions are the five resource-type labels crossed with five difficulty steps (25 values).

## Training result
* Episodes: **2500**
* Visited abstract states: **53**
* Mean episode reward (first 200): **-9.87**
* Mean episode reward (last 200): **3.56**
* Improvement: **+13.42**

Learner dynamics and all reported outcomes are simulated; they do not demonstrate real learning gains.