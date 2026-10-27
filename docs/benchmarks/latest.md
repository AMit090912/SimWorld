# SimWorld benchmark (latest run)

Generated 2026-10-27 06:33 UTC from recorded runs. Seeds: 7, 11, 23.
Every number below comes from the SimWorld API; none are self-reported by an agent.

## Composite scores

| Scenario | Agent | Mean score | Std | Runs |
| --- | --- | --- | --- | --- |
| city-logistics/standard | Disruption-Aware Dispatcher | 77.7 | ±3.0 | 3 |
| city-logistics/standard | Greedy Nearest Delivery | 78.3 | ±1.4 | 3 |
| city-logistics/standard | Static Shortest Path (blind) | 62.0 | ±1.4 | 3 |
| city-logistics/disruption-storm | Disruption-Aware Dispatcher | 75.5 | ±2.8 | 3 |
| city-logistics/disruption-storm | Greedy Nearest Delivery | 76.4 | ±2.3 | 3 |
| city-logistics/disruption-storm | Static Shortest Path (blind) | 62.7 | ±2.3 | 3 |
| traffic-control/steady | Adaptive Pressure Controller | 81.5 | ±0.8 | 3 |
| traffic-control/steady | Fixed-Cycle Timer | 71.6 | ±0.4 | 3 |

## City logistics components

| Scenario | Agent | Completion | On time | Fuel (L) | Invalid | Latency (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| city-logistics/standard | Disruption-Aware Dispatcher | 100% | 62% | 9.13 | 0.0 | 0 |
| city-logistics/standard | Greedy Nearest Delivery | 100% | 67% | 10.12 | 0.0 | 0 |
| city-logistics/standard | Static Shortest Path (blind) | 86% | 62% | 7.92 | 93.3 | 0 |
| city-logistics/disruption-storm | Disruption-Aware Dispatcher | 100% | 52% | 9.68 | 0.0 | 0 |
| city-logistics/disruption-storm | Greedy Nearest Delivery | 100% | 57% | 9.79 | 0.0 | 0 |
| city-logistics/disruption-storm | Static Shortest Path (blind) | 86% | 57% | 6.93 | 100.0 | 0 |

## Traffic control components

| Scenario | Agent | Throughput | Avg wait (ticks) | Avg queue | Violations | Latency (ms) |
| --- | --- | --- | --- | --- | --- | --- |
| traffic-control/steady | Adaptive Pressure Controller | 96% | 4.3 | 5.6 | 0.0 | 0 |
| traffic-control/steady | Fixed-Cycle Timer | 81% | 3.1 | 17.0 | 0.0 | 0 |

## Failures worth reading

- **ef3553001a6b** · city-logistics/standard · seed 7 · Disruption-Aware Dispatcher · score 80.26: 2 package(s) delivered after their deadline.
- **c9e78aa3b53a** · city-logistics/standard · seed 7 · Greedy Nearest Delivery · score 79.29: 2 package(s) delivered after their deadline.
- **45fc9604a12f** · city-logistics/standard · seed 7 · Static Shortest Path (blind) · score 61.08: 1 package(s) not delivered before the shift ended.; 2 package(s) delivered after their deadline.; 93 action(s) rejected by the engine (insufficient_fuel=68, road_closed=25).; Van ended the run with under 0.5 L of fuel.
- **106c4ff28d7a** · city-logistics/standard · seed 11 · Disruption-Aware Dispatcher · score 73.57: 4 package(s) delivered after their deadline.
- **892ff8eb8622** · city-logistics/standard · seed 11 · Greedy Nearest Delivery · score 76.43: 3 package(s) delivered after their deadline.
- **f7892faf4b15** · city-logistics/standard · seed 11 · Static Shortest Path (blind) · score 61.08: 1 package(s) not delivered before the shift ended.; 2 package(s) delivered after their deadline.; 94 action(s) rejected by the engine (insufficient_fuel=94).; Van ended the run with under 0.5 L of fuel.
- **19fe2e93f7e7** · city-logistics/standard · seed 23 · Disruption-Aware Dispatcher · score 79.29: 2 package(s) delivered after their deadline.
- **8d7f86982158** · city-logistics/standard · seed 23 · Greedy Nearest Delivery · score 79.29: 2 package(s) delivered after their deadline.
- **69dd37f37921** · city-logistics/standard · seed 23 · Static Shortest Path (blind) · score 63.94: 1 package(s) not delivered before the shift ended.; 1 package(s) delivered after their deadline.; 93 action(s) rejected by the engine (insufficient_fuel=81, road_closed=12).; Van ended the run with under 0.5 L of fuel.
- **b7965bb05a38** · city-logistics/disruption-storm · seed 7 · Disruption-Aware Dispatcher · score 79.44: 2 package(s) delivered after their deadline.
- **5a1bc57c206a** · city-logistics/disruption-storm · seed 7 · Greedy Nearest Delivery · score 76.43: 3 package(s) delivered after their deadline.
- **afd2e16ca821** · city-logistics/disruption-storm · seed 7 · Static Shortest Path (blind) · score 62.73: 1 package(s) not delivered before the shift ended.; 2 package(s) delivered after their deadline.; 100 action(s) rejected by the engine (insufficient_fuel=100).; Van ended the run with under 0.5 L of fuel.
- **64c5dcfa2fe1** · city-logistics/disruption-storm · seed 11 · Disruption-Aware Dispatcher · score 73.57: 4 package(s) delivered after their deadline.
- **1eaf38b7c755** · city-logistics/disruption-storm · seed 11 · Greedy Nearest Delivery · score 73.57: 4 package(s) delivered after their deadline.
- **d50a08fdce7b** · city-logistics/disruption-storm · seed 11 · Static Shortest Path (blind) · score 59.88: 1 package(s) not delivered before the shift ended.; 3 package(s) delivered after their deadline.; 100 action(s) rejected by the engine (insufficient_fuel=79, road_closed=21).; Van ended the run with under 0.5 L of fuel.
- **4811d5b8f4d7** · city-logistics/disruption-storm · seed 23 · Disruption-Aware Dispatcher · score 73.57: 4 package(s) delivered after their deadline.
- **235f2227bb53** · city-logistics/disruption-storm · seed 23 · Greedy Nearest Delivery · score 79.29: 2 package(s) delivered after their deadline.
- **75fed6f4a3ac** · city-logistics/disruption-storm · seed 23 · Static Shortest Path (blind) · score 65.59: 1 package(s) not delivered before the shift ended.; 1 package(s) delivered after their deadline.; 100 action(s) rejected by the engine (insufficient_fuel=100).; Van ended the run with under 0.5 L of fuel.
- **5fdcb2d5e812** · traffic-control/steady · seed 11 · Fixed-Cycle Timer · score 71.15: Only 80% of arriving vehicles cleared an intersection.

## Evidence

Open any run in the SimWorld UI (`/runs/<id>`) to replay every recorded transition.
Experiments used identical seeds for every agent in a scenario.
