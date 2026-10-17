# Comparative Testing & Benchmarking Report: Baseline Dijkstra vs. Enhanced Dijkstra (EDSPA)

**Project:** MaternaCare (رِعَايَة) — Intelligent Maternal Healthcare Access & Hospital Selection Platform  
**Workstream:** Team 3: Evaluation & Integration  
**Role:** **Member 5 — Comparative Testing**  
**Date:** October 2026  
**Repository Branch:** `GIS-Features`  

---

## 1. Executive Summary

As part of **Team 3 (Evaluation & Integration)**, Member 5 is responsible for **Comparative Testing**:
1. Designing a comprehensive, clinically grounded suite of test cases across the Upper Egypt road network.
2. Benchmarking the **Baseline Dijkstra Algorithm** (Team 1) against the **Enhanced Dijkstra Shortest Path Algorithm (EDSPA)** (Team 2) using identical origin points, candidate hospital destinations, and road network topology.
3. Evaluating comparative performance across distance, estimated travel time ($min$), search space exploration (settled nodes), and computational runtime ($ms$).

### Key Empirical Findings (30 Test Cases Across 2.3M Node Upper Egypt Graph)
* **Optimality & Correctness:** **100.0% Exact Match** (30/30). Both algorithms identified the **identical nearest hospital** and computed the **identical minimum travel time** in all test scenarios.
* **Search Space Pruning:** Enhanced Dijkstra settled an average of **6,370 nodes** compared to **2,017,284 nodes** for Baseline Dijkstra — achieving an average **98.89% search space reduction** (a **316.7× pruning factor**).
* **Runtime Execution Performance:** Average execution time dropped from **5,563.80 ms (~5.56 s)** in Baseline down to **17.71 ms (~0.018 s)** in Enhanced Dijkstra — an average **753.3× speedup factor** (median: **462.1×**, max: **3,414.2×**).
* **Latency Impact for Mobile Clients:** A 5.5-second lag is prohibitive for emergency mobile apps; a 17-millisecond response delivers instant, zero-lag hospital recommendations.

---

## 2. Test Case Design & Methodology

### 2.1 The Test Environment & Graph Parameters
* **Road Network Coverage:** Upper Egypt Regional Corridor (Beni Suef, Minya, Assiut, Sohag, Qena, Luxor, Aswan).
* **Total Graph Vertices (Nodes):** $2,300,821$ road intersections.
* **Total Graph Edges (Directed Connections):** $4,746,637$ road segments.
* **Hospital Facilities Snapped to Graph:** $728$ verified facilities mapped across $666$ unique road nodes.
* **Graph Weight Metric:** Dynamic travel time in seconds ($t = \frac{\text{length (m)}}{\text{speed (m/s)}}$), accounting for road speed limits and classifications.

### 2.2 Test Case Stratification (Distance & Urgency Tiers)
To ensure the evaluation represents real-world clinical conditions, the 30 test cases were stratified into four distinct operational tiers:

| Tier | Category | Travel Time Window | Clinical / Geographic Meaning | Sample Size |
| :---: | :--- | :---: | :--- | :---: |
| **Tier 1** | **Immediate Urban Emergency** | $< 5.0\text{ min}$ | High-density urban centers (Assiut, Minya, Sohag); patient is within immediate reach of a primary or district hospital. | 9 cases (30%) |
| **Tier 2** | **Short-Range Transit** | $5.0\text{--}10.0\text{ min}$ | Standard town-to-district emergency transit across paved primary/secondary urban roads. | 12 cases (40%) |
| **Tier 3** | **Mid-Range Regional Transit** | $10.0\text{--}20.0\text{ min}$ | Inter-village or suburban navigation involving canal roads and secondary regional connectors. | 8 cases (27%) |
| **Tier 4** | **Long-Range / Remote Rural** | $> 20.0\text{ min}$ | Peripheral agricultural and desert highway corridors with sparse facility density. | 1 case (3%) |

---

## 3. Comparative Benchmarking Results

### 3.1 Global Performance Comparison (30-Case Overview)

| Evaluation Metric | Baseline Dijkstra (Team 1) | Enhanced Dijkstra / EDSPA (Team 2) | Improvement / Delta |
| :--- | :---: | :---: | :---: |
| **Optimal Path Cost Agreement** | $100.0\%$ | $100.0\%$ | **Identical (100% Agreement)** |
| **Hospital Selection Agreement** | $100.0\%$ | $100.0\%$ | **Identical (30 / 30)** |
| **Average Settled Graph Nodes** | $2,017,284.5\text{ nodes}$ | $6,370.2\text{ nodes}$ | **-98.89% (316.7× fewer nodes)** |
| **Median Settled Graph Nodes** | $2,157,051.0\text{ nodes}$ | $4,349.0\text{ nodes}$ | **-99.80% search reduction** |
| **Minimum Settled Nodes** | $42,438\text{ nodes}$ | $372\text{ nodes}$ | **99.12% reduction** |
| **Maximum Settled Nodes** | $2,157,051\text{ nodes}$ | $26,274\text{ nodes}$ | **98.78% reduction** |
| **Average Execution Time ($ms$)** | $5,563.80\text{ ms}$ ($5.56\text{ s}$) | $17.71\text{ ms}$ ($0.018\text{ s}$) | **753.3× faster (98.86% reduction)** |
| **Median Execution Time ($ms$)** | $5,762.26\text{ ms}$ | $12.70\text{ ms}$ | **462.1× faster** |
| **Peak Single-Case Speedup** | $5,594.31\text{ ms}$ | $1.74\text{ ms}$ | **3,414.2× speedup** (Case #20) |

---

### 3.2 Performance Breakdown by Distance Tier

```
Tier 1 (< 5 min)   : ████████████████████████████████████ 1,576.4x Speedup (Avg 6.7 ms vs 5,910 ms)
Tier 2 (5-10 min)  : ████████████ 557.8x Speedup (Avg 12.6 ms vs 5,665 ms)
Tier 3 (10-20 min) : ████ 204.0x Speedup (Avg 27.5 ms vs 4,960 ms)
Tier 4 (> 20 min)  : █ 86.0x Speedup (Avg 67.1 ms vs 5,769 ms)
```

#### Detailed Breakdown Table:
| Operational Tier | Test Count | Avg Travel Time ($min$) | Avg Baseline Settled | Avg Enhanced Settled | Avg Baseline Time ($ms$) | Avg Enhanced Time ($ms$) | Mean Speedup Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Tier 1: $< 5\text{ min}$** | 9 | $2.91\text{ min}$ | $2,157,051.0$ | $1,544.7$ | $5,910.42\text{ ms}$ | $6.71\text{ ms}$ | **$1,576.4\times$** |
| **Tier 2: $5\text{--}10\text{ min}$** | 12 | $6.97\text{ min}$ | $1,980,833.2$ | $5,431.1$ | $5,664.83\text{ ms}$ | $12.59\text{ ms}$ | **$557.8\times$** |
| **Tier 3: $10\text{--}20\text{ min}$** | 8 | $14.74\text{ min}$ | $1,897,253.1$ | $10,875.0$ | $4,959.85\text{ ms}$ | $27.50\text{ ms}$ | **$204.0\times$** |
| **Tier 4: $> 20\text{ min}$** | 1 | $70.22\text{ min}$ | $2,157,051.0$ | $26,274.0$ | $5,769.18\text{ ms}$ | $67.10\text{ ms}$ | **$86.0\times$** |

---

## 4. In-Depth Algorithmic Analysis

### 4.1 Why Enhanced Dijkstra (EDSPA) Is Provably Optimal
A common concern in heuristic graph optimization is whether early stopping sacrifices route optimality. 
* **The Theorem:** In a non-negative weighted directed graph $G = (V, E)$, Dijkstra's priority queue pops vertices in monotonically non-decreasing order of cost:
  $$d(s, u_1) \le d(s, u_2) \le \dots \le d(s, u_k)$$
* **The EDSPA Proof:** If an algorithm halts the very first moment that any vertex $u \in \text{EndList}$ is dequeued:
  $$\forall v \in \text{EndList} \setminus \{u\}, \quad d(s, v) \ge d(s, u)$$
* **Conclusion:** The first popped hospital is **guaranteed** to have the minimum travel time. The remaining $2.15\text{ million}$ nodes in the graph cannot yield a shorter path. This is validated by the **$100.0\%$ match rate across all 30 empirical tests**.

### 4.2 Why Baseline Dijkstra Incurs Severe Latency Overhead
* The baseline implementation continues searching through the graph to ensure all nodes are settled, exploring an average of **$2.01\text{ million nodes}$**.
* In an emergency mobile navigation scenario, forcing the user to wait **$5.5\text{ seconds}$** over a mobile network connection degrades user experience and introduces critical emergency delay.
* EDSPA restricts exploration to a localized spherical frontier around the patient, terminating in **$<18\text{ ms}$** without allocating gigabytes of priority queue memory.

---

## 5. Handover Recommendations for Member 6 (Validation & Integration)

Based on the empirical findings of Member 5, the following technical recommendations are passed to **Member 6 (Validation & Technical Integration)**:

1. **Integration into Mobile API:**
   * Replace the baseline Dijkstra engine with the **EDSPA routine** in the production backend routing microservice (`FastAPI`).
   * The sub-20ms latency allows real-time route re-calculation if traffic conditions change.

2. **Edge Case Handling for Disconnected Subgraphs:**
   * In Test Cases #0 and #1, baseline settled nodes dropped to $78,668$ and $42,438$ because the patient was snapped onto a small isolated component.
   * **Recommendation for Member 6:** Implement a pre-check confirming the patient snaps to the **strongly connected main component** ($>99.2\%$ of Upper Egypt roads) before initiating Dijkstra.

3. **Multi-Criteria Extension (Milestone 1 Tie-in):**
   * Currently, EDSPA stops at the *geographically closest* hospital node.
   * Combine EDSPA with our **E2SFCA / Clinical Tier Filtering**: Filter the `EndList` in memory beforehand (e.g., keeping only CEmONC hospitals with 24/7 ICU/surgery for emergency maternal triage) so that EDSPA halts at the nearest **clinically suitable** hospital rather than just any dispensary.

---

## 6. Deliverables Summary
* **Report:** `Evaluation & Comparative Testing/Comparative_Testing_Report.md`
* **Benchmark Dataset:** `Evaluation & Comparative Testing/comparative_test_results.csv`
* **Analysis Notebook:** `Evaluation & Comparative Testing/Team3_Member5_Comparative_Testing.ipynb`
* **Visualizations:**
  * `runtime_comparison.png`
  * `settled_nodes_comparison.png`
  * `speedup_by_tier.png`
