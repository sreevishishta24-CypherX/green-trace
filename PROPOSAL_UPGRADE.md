GREENTRACE — Proposal Upgrades and Focused Roadmap
=================================================

Goal
----
Strengthen GREENTRACE's submission by narrowing the MVP, specifying how the NLP and CV components will be trained and validated, adding legal/ethical safeguards, and outlining partnerships and a short roadmap so a student team can execute the pilot.

1) Narrowed MVP (recommended)
--------------------------------
- Scope: Start with a single, well-defined EC condition type — river/stream buffer violations (e.g., any permanent project footprint within X metres of a mapped watercourse).
- Geography: Pilot a single state/region with good public data coverage (example: choose one state with accessible PARIVESH records and a manageable number of ECs).
- Data inputs: EC PDFs (text or scanned), project point/parcel, PARIVESH project metadata, Sentinel-2 optical + Sentinel-1 SAR for cloudy periods.
- MVP deliverable: a dashboard that (a) extracts the buffer requirement from an EC, (b) overlays buffer on satellite-derived waterbodies, (c) scores and flags potential buffer infringements, and (d) surfaces a human-review workflow for verification.

2) Training-data & NLP strategy
-------------------------------
- Prioritize quantitative extractions: numeric distances ("500 m", "within 100 metres"), named features ("river", "stream"), and explicit spatial constraints ("no activity within X of waterbody").
- Heuristic bootstrapping: implement rule-based regex and gazetteer rules to seed labeled examples (fast wins for numeric & distance phrases).
- Distant supervision & weak labels: align EC metadata (if PARIVESH lists conditions) with parsed text to produce noisy labels for an initial training set.
- Small, high-quality human-labeled seed: recruit annotators (team members or paid microtasks) to label ~500–2,000 EC clauses covering the pilot region for fine-tuning.
- Model architecture: start with an off-the-shelf legal/Indian-English transformer (e.g., LegalBERT / multilingual BERT) and fine-tune for slot-filling (entity + value extraction). Use a hybrid approach: rule-based for high-confidence numeric fields, ML for ambiguous language.
- Active learning: run the model on unlabeled ECs and surface low-confidence or novel-phrase examples for human annotation to grow the labeled set efficiently.

3) Computer-vision (satellite) strategy
--------------------------------------
- Use NDWI + thresholding as a baseline for water detection from Sentinel-2; use Sentinel-1 SAR-derived water masks for monsoon/cloudy periods.
- Build a small labeled dataset for the pilot region by combining: public waterbody layers (OpenStreetMap, government), synthetic masks, and manual correction for ~200–500 scenes.
- Model approach: classical segmentation + post-processing (morphology + connectivity) is sufficient for MVP; a lightweight UNet on NDWI/RGB/SAR stacks can be added if needed.
- Change detection: compare seasonal baselines (pre-construction) to recent imagery using difference-in-time metrics and temporal smoothing to avoid false positives from seasonal changes.

4) Validation methodology & accuracy thresholds
------------------------------------------------
- NLP validation:
  - Holdout test set from the pilot region (20% of labeled documents).
  - Metrics: precision/recall/F1 for slot extraction. Target thresholds for automated output:
    - Quantitative fields (numeric distances): precision >= 0.90, recall >= 0.85.
    - Qualitative triggers ("adequate measures", "no discharge"): precision >= 0.80, recall >= 0.75.
  - Human-review trigger: any extraction with model confidence below 0.90 for numeric fields or below 0.80 for qualitative fields goes to a verifier.
- CV validation:
  - Use manual annotation of 200–500 image patches to compute pixel-level IoU and object-level precision/recall.
  - Pilot thresholds: precision >= 0.85 and recall >= 0.75 for water detection. For project-level infringement flagging, require score thresholds tuned to prioritize precision (e.g., only flag if risk score >= 0.6 AND CV confidence >= 0.8).
- End-to-end validation:
  - Create a curated test set of projects with known outcomes (if available) or manually labeled events.
  - Measure false-positive and false-negative rates at the case-level; tune to conservative operation (prefer human workload over false accusations).

5) Legal & ethical safeguards
----------------------------
- Conservative wording: UI and reports must use wording like "possible non-compliance" and show explicit evidence layers rather than definitive legal conclusions.
- Audit trail & export: every extraction and CV result must include provenance (source PDF page, model confidence scores, image timestamps) and be exportable for human review.
- Human-in-the-loop gates: require human sign-off before any public allegation or sharing with third parties. Automate minor alerts for internal triage only.
- Privacy & data policy: do not publish private identifiers; comply with national privacy laws and maintain a takedown/rebuttal workflow for project owners.
- Legal counsel & MoU: seek a simple legal review and an MoU template for pilots clarifying responsibilities and disclaimers before sharing findings externally.

6) Partnerships & action pathways
---------------------------------
- Shortlist partners to approach for the pilot: local environmental NGOs, a state pollution control board contact, an academic partner (remote sensing lab), an NGT petitioner group, and one responsible-lending contact (sustainability officer at a bank).
- Pilot MOUs: offer a single-state pilot where partners provide a small set of ECs and feedback on flagged cases; in return provide curated evidence packages.
- Enforcement pathway: document recommended next steps after a verified flag — e.g., NGO files a petition, lender triggers due-diligence review — and include partner-specific workflows.

7) Prioritization & resource allocation
--------------------------------------
- Prioritize projects by risk score combining: ecological sensitivity (presence of water/forest), project footprint size, and financial exposure (if lender data available).
- For monitoring cadence, run weekly checks for high-risk projects, monthly for medium risk, and quarterly for low risk during the pilot.

8) Roadmap (6 months, student-team friendly)
-------------------------------------------
- Month 0–1: Project setup, pick pilot region, collect ECs and PARIVESH metadata, implement simple regex extractor, build small labeling UI.
- Month 1–2: Label seed set (~500–1,000 clauses), bootstrapped NLP model training, baseline NDWI + SAR water masks, baseline dashboard wireframe.
- Month 2–4: Active learning loop to grow labeled data, CV model improvements, integrate NLP + CV into end-to-end pipeline, run initial validation and tune thresholds.
- Month 4–6: Partner pilot, human-in-the-loop verification, iterate on UX and reporting templates, document outcomes and prepare materials for next-round scaling.

9) Success metrics for the pilot
-------------------------------
- NLP slot-extraction F1 (quantitative) >= 0.88 on holdout.
- CV water detection precision >= 0.85 on pilot annotations.
- End-to-end case precision >= 0.80 (after human verification gate) — i.e., of cases escalated as "possible non-compliance," >=80% are judged by partners/experts as worthy of further action.
- Usability metric: partner verifies >=70% of flagged cases are useful (partner feedback survey).

10) Deliverables
----------------
- `PROPOSAL_UPGRADE.md` (this file): tightened scope, training, validation, legal safeguards, partnerships and roadmap.
- Minimal dashboard update inside the repo: a pilot configuration that limits workflows to the selected region and buffer ruleset.

Next steps I can take now (pick one):
- Implement the regex-based numeric extractor and annotation UI for EC clauses.
- Create a small labeling task template and starter dataset for the pilot region.
- Wire the pilot risk-scoring configuration into the existing demo dashboard in the repo.

If you want, I can start by creating the annotation schema and a labeling UI + starter dataset for the pilot region.
