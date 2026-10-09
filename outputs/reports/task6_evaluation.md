# Task 6 -- Cross-Graph Policy Evaluation

Evaluation used **100 simulated learners** from topic graphs held out from model training, with 30 interactions per policy.

| Policy | Mean gain | SD | Gain/hour | Engagement | Ability gap | Level gap | Engagement gap | Mastery gap | Final mastery Gini |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Static curriculum | 0.1104 | 0.0256 | 0.0100 | 0.4238 | 0.0128 | 0.0269 | 0.0011 | 0.0548 | 0.2008 |
| Behavior policy | 0.1005 | 0.0247 | 0.0092 | 0.4135 | 0.0028 | 0.0119 | 0.0032 | 0.0320 | 0.2224 |
| ZPD heuristic | 0.1048 | 0.0279 | 0.0108 | 0.4312 | 0.0045 | 0.0365 | 0.0025 | 0.0411 | 0.2063 |
| Q-learning | 0.1062 | 0.0271 | 0.0150 | 0.4406 | 0.0032 | 0.0345 | 0.0120 | 0.0459 | 0.2019 |
| Hybrid optimizer | 0.1218 | 0.0359 | 0.0108 | 0.5254 | 0.0051 | 0.0541 | 0.0000 | 0.0576 | 0.1861 |

The four group gaps are absolute differences in mean simulated mastery gain between the named high/low groups. The learner-level gap compares simulated learners below and above level 50. These are measurements, not proof of fairness.

The coverage term in Task 5 rewards useful difficulty range and engaging resource types when mastery or engagement is low; it does not guarantee equal outcomes.

Hybrid optimizer versus static curriculum, paired by learner: t=4.540, p=1.588e-05.

All learners and gains in this evaluation are simulated. These numbers do not establish real-world learning gains or fairness.