**IO Crosscheck**

PLC-to-IO List Device Verification Engine

Product Requirements Document

  ---------------------- ------------------------------------------------
  **Field**              **Value**

  Version                1.0

  Date                   February 5, 2026

  Author                 Tyler (Automation Engineer) / Claude (AI
                         Assistant)

  Project Context        CHRL Xfer System --- PLC5 to ControlLogix
                         Migration

  Classification         Mission-Critical --- Multi-Million Dollar
                         Project Backbone

  Accuracy Requirement   100% deterministic verification (zero tolerance
                         for false positives/negatives)
  ---------------------- ------------------------------------------------

**1. Executive Summary**

**IO Crosscheck** is a deterministic device verification engine
purpose-built for PLC migration projects. It answers one critical
question for every device in scope: **\"Does this device exist in the
PLC program, the IO List, or both?\"**

This tool was born from a real-world need on the CHRL Xfer System
migration (PLC5 to ControlLogix). The existing verification
process---manually cross-referencing a 29,000-line RSLogix 5000 tag
export CSV against a 3,800-row IO List spreadsheet---is error-prone,
time-consuming, and fundamentally unsuitable for a project where
incorrect device mapping can lead to commissioning failures, safety
incidents, or costly rework.

This PRD defines a tool that uses **deterministic, rule-based
matching---not probabilistic AI or machine learning**---to produce
results that are auditable, repeatable, and 100% verifiable by a human
engineer. Every match or non-match is traceable to a specific rule and
specific source data.

**2. Problem Statement**

**2.1 The Verification Challenge**

During a PLC5-to-ControlLogix migration, engineers must verify that
every physical IO device that exists in the legacy IO List has been
properly configured in the new ControlLogix PLC program, and vice versa.
The CHRL Xfer System involves:

-   **3,261 active IO points** across 7 IO panels (X1--X7) and 22+ racks

-   **9,013 PLC tags** in the ControlLogix program, plus 2,629 tag
    comments and 6,474 alias entries

-   **569 spare points** that must be correctly identified and excluded
    from mismatch reporting

-   **142 EtherNet/IP module tags** (E300 overloads, VFDs, IP devices)
    that exist only in the PLC with no IO List counterpart

-   **Mixed IO architectures**: PLC5-style rack addressing
    (Rack0_Group0_Slot0_IO.READ\[4\]) and ControlLogix-style
    (Rack11:I.DATA\[3\].13)

Manual cross-referencing of this data is estimated at 40--80 hours of
focused engineering time with a high risk of human error, especially
given naming convention inconsistencies between sources (e.g.,
\"TSV22_EV\" in IO List vs \"TSV22\" in PLC comments; case differences
like \"Data\" vs \"DATA\").

**2.2 Why Not Data Science / ML?**

After thorough analysis of the actual data, we explicitly reject fuzzy
matching, NLP similarity scoring, and machine learning approaches for
the core matching engine. Here is why:

  ----------------- ------------------------------------------------------
  **Approach**      **Why It Fails for This Use Case**

  Fuzzy String      \"LT611\" and \"LT612\" are Levenshtein distance 1
  Matching          apart but are completely different devices. Fuzzy
  (Levenshtein,     matching would produce catastrophic false positives in
  Jaro-Winkler)     an environment where every tag name is a short
                    alphanumeric code with high structural similarity.

  TF-IDF / Cosine   Tag names are atomic identifiers, not natural language
  Similarity        documents. There is no semantic content to vectorize.
                    \"E300_P621\" and \"P621\" have low cosine similarity
                    despite being the same device.

  Machine Learning  Requires labeled training data that doesn't exist.
  Classification    Each migration project has unique naming conventions.
                    A model trained on one plant's data would not
                    generalize. More critically, an ML model cannot
                    guarantee 100% accuracy---it can only estimate
                    probabilities.

  Embedding-Based   Same fundamental problem: these are structured
  Similarity (LLM)  identifiers, not semantic text. LLM embeddings would
                    treat \"P621\" and \"P623\" as nearly identical when
                    they are different pumps.
  ----------------- ------------------------------------------------------

**The correct approach is deterministic, rule-based matching** that
encodes the actual naming conventions and addressing schemes used in
Rockwell Automation systems. This is a structured data reconciliation
problem, not a pattern recognition problem.

**3. Solution Architecture**

**3.1 Core Design Philosophy**

IO Crosscheck operates as a **multi-strategy deterministic matching
engine**. Each device is evaluated against a cascade of matching rules,
each targeting a specific data relationship. A match is only declared
when an exact, unambiguous correspondence is found. Every result carries
a full audit trail showing which rule matched, what data was compared,
and the confidence basis.

**3.2 System Architecture**

  --------------- ------------------ ----------------------------------------
  **Layer**       **Component**      **Responsibility**

  Input Parsers   CSV Tag Parser     Parses RSLogix 5000 CSV tag export;
                                     extracts TAG, COMMENT, ALIAS, and
                                     RCOMMENT records with full metadata
                                     (scope, name, datatype, description,
                                     specifier)

  Input Parsers   XLSX IO List       Reads ESCO List sheet; normalizes panel,
                  Parser             rack, group, slot, channel, PLC IO
                                     address, IO tag, device tag, module
                                     type, module, and range data

  Input Parsers   Rack Layout Parser Reads Rack Layouts sheet to extract the
                                     physical slot-to-device mapping as a
                                     cross-reference source

  Normalization   Tag Normalizer     Canonicalizes tag names: case-folding,
                                     suffix stripping (\_EV, \_MC, \_AUX,
                                     \_ZSO, \_ZSC, \_Pulse, \_In, \_Input,
                                     \_Out, \_Old, \_Pos), whitespace
                                     trimming

  Normalization   Address Normalizer Converts PLC5 and CLX address formats to
                                     a common canonical form for comparison

  Matching Engine Rule Cascade       Executes matching strategies in priority
                                     order (see Section 4)

  Matching Engine Conflict Resolver  Detects and flags cases where multiple
                                     rules produce contradictory results

  Output          Classification     Assigns each device to PLC Only, IO List
                  Engine             Only, or Both with audit metadata

  Output          Report Generator   Produces verification reports in XLSX
                                     and HTML with filtering, sorting, and
                                     drill-down

  Output          Audit Logger       Records every matching decision with
                                     rule ID, source data, and match basis
  --------------- ------------------ ----------------------------------------

**4. Matching Strategies (Rule Cascade)**

The matching engine evaluates each IO List device against the PLC data
using the following strategies in priority order. A device is classified
as \"Both\" on the first successful match. If no strategy matches, the
device is classified as \"IO List Only\". PLC tags with no IO List match
are classified as \"PLC Only\".

**4.1 Strategy 1: Direct Address Match (CLX Rack IO)**

For ControlLogix-format rack IO, the IO List's PLC IO Address column
(e.g., \"Rack11:I.Data\[3\].13\") is matched against PLC COMMENT
specifiers (e.g., \"Rack11:I.DATA\[3\].13\"). Matching is
case-insensitive. This is the highest-confidence match because it uses
the actual hardware address.

  ------------------ ----------------------------------------------------
  **Parameter**      **Detail**

  Applies To         CLX-format rack IO addresses
                     (Rack\<N\>:\<I\|O\>.Data\[\<word\>\].\<bit\>)

  Match Source       PLC COMMENT entries on Rack-level TAG specifiers

  Normalization      Case-insensitive comparison; \"Data\" matches
                     \"DATA\"

  Confidence         Exact --- hardware address is deterministic

  Coverage (CHRL)    113 of 3,007 CLX-format points (only where PLC
                     comments exist)

  Validation         Cross-check that the PLC comment description matches
                     the IO List device tag (flags mismatches like
                     FT656B_Pulse ≠ HLSTL5C for human review)
  ------------------ ----------------------------------------------------

**4.2 Strategy 2: PLC5 Rack Address Match**

For PLC5-format rack IO, the IO List's PLC IO Address (e.g.,
\"Rack0_Group0_Slot0_IO.READ\[4\]\") is matched against PLC TAG names
that follow the same pattern. This captures the 254 PLC5-format points
in the IO List.

  ------------------ ------------------------------------------------------------------
  **Parameter**      **Detail**

  Applies To         PLC5-format addresses
                     (Rack\<N\>\_Group\<G\>\_Slot\<S\>\_IO.\<READ\|WRITE\>\[\<CH\>\])

  Match Source       PLC TAG entries with matching base names

  Normalization      Decompose to {rack, group, slot, channel} tuple for comparison

  Confidence         Exact --- hardware address tuple is deterministic

  Coverage (CHRL)    254 PLC5-format points
  ------------------ ------------------------------------------------------------------

**4.3 Strategy 3: Rack-Level TAG Existence**

For IO List entries whose specific bit/channel address has no PLC
COMMENT, verify that the parent Rack TAG exists in the PLC (e.g.,
\"Rack11:I\" exists as a TAG entry). This confirms the physical rack
connection is configured, even if individual point-level comments
haven't been added yet. This produces a weaker but still valuable match
classified as \"Rack Exists, Point Unconfirmed\" rather than a full
\"Both\".

  ------------------ ----------------------------------------------------
  **Parameter**      **Detail**

  Applies To         CLX-format IO addresses with no Strategy 1 match

  Match Source       PLC TAG entries for Rack\<N\>:I or Rack\<N\>:O

  Confidence         Partial --- rack exists but individual point not
                     verified

  Coverage (CHRL)    \~2,894 points where rack TAG exists but no
                     per-point COMMENT

  Classification     \"Both (Rack Only)\" --- distinct from full \"Both\"
                     for engineering review
  ------------------ ----------------------------------------------------

**4.4 Strategy 4: EtherNet/IP Module Tag Extraction**

PLC tags prefixed with E300\_, VFD\_, IPDev\_, or IPDEV\_ contain
embedded device identifiers. These are extracted and matched against IO
List device tags. Example: PLC tag \"E300_P621:I\" contains device
\"P621\"; IO List device tag \"P621\" matches.

  ------------------ ----------------------------------------------------
  **Parameter**      **Detail**

  Applies To         PLC TAGs with prefixes: E300\_, VFD\_, IPDev\_,
                     IPDEV\_

  Match Source       IO List Device Tag column (column J)

  Normalization      Strip prefix, case-insensitive comparison

  Confidence         Exact --- after prefix stripping, names must match
                     exactly

  Coverage (CHRL)    142 PLC ENet module tags; 13 match IO List device
                     tags

  Note               Many ENet devices are PLC-only (overloads, VFDs not
                     in legacy IO List)
  ------------------ ----------------------------------------------------

**4.5 Strategy 5: Tag Name Normalization Match**

IO List IO tags and device tags are compared against all PLC tag base
names after applying normalization rules. Normalization strips known
suffixes (\_EV, \_MC, \_AUX, \_ZSO, \_ZSC, \_Pulse, \_In, \_Input,
\_Out, \_Old, \_Pos, \_FailedToClose, \_FailedToOpen, \_OnTimer,
\_OffTimer, \_Monitor, \_Failed) and performs case-insensitive
comparison.

  ------------------ ----------------------------------------------------
  **Parameter**      **Detail**

  Applies To         All IO List devices not matched by Strategies 1--4

  Match Source       All PLC TAG base names (before : suffix), all PLC
                     COMMENT descriptions

  Normalization      Strip IO-type suffixes, case-fold, trim whitespace

  Confidence         High --- requires exact base name match after
                     normalization

  Example            IO: \"TSV22_EV\" → base \"TSV22\"; PLC comment:
                     \"TSV22\" → Match

  Validation         Flags partial matches (e.g., IO tag found in PLC tag
                     but not exact) for human review
  ------------------ ----------------------------------------------------

**4.6 Strategy 6: Rack Layout Cross-Reference**

The Rack Layouts sheet provides a physical view of every slot and
channel mapped to its device. This serves as a third independent data
source for triangulation. If an IO List device appears in the Rack
Layout at the expected panel/rack/slot position but not in the PLC, it
provides evidence for a genuine \"IO List Only\" classification.
Conversely, if it appears in both IO List and Rack Layout but not PLC,
it strongly suggests a PLC configuration gap.

**4.7 Strategy Cascade Summary**

  -------------- --------------------- ---------------- ---------------- ----------------
  **Priority**   **Strategy**          **Confidence**   **Match Type**   **Est.
                                                                         Coverage**

  1              Direct CLX Address    Exact            Address ↔        \~113 points
                 Match                                  Comment          

  2              PLC5 Address Match    Exact            Address ↔ TAG    \~254 points

  3              Rack TAG Existence    Partial          Address → Rack   \~2,894 points
                                                        TAG              

  4              ENet Module           Exact            Prefix-strip ↔   \~142 PLC tags
                 Extraction                             Device Tag       

  5              Tag Name              High             Normalized name  Remaining
                 Normalization                          match            

  6              Rack Layout           Supporting       Physical layout  All
                 Triangulation                          cross-ref        
  -------------- --------------------- ---------------- ---------------- ----------------

**5. Data Analysis Findings (CHRL Xfer System)**

The following findings are based on analysis of the actual project
files: XFERSYS_Tags.CSV (29,025 lines) and CHRL_Xfer_IO_List_00 (3,870
rows in ESCO List sheet).

**5.1 PLC Tag Export Structure**

  --------------------- ------------- ------------------------------------
  **Record Type**       **Count**     **Purpose**

  TAG                   9,013         Module-level IO tags, program tags,
                        (unique)      UDTs, arrays

  COMMENT               2,629         Bit/channel-level descriptions on
                                      Rack IO tags

  ALIAS                 6,474         Slot-level aliases for ControlLogix
                                      racks (Rack25, Rack26)

  RCOMMENT              Various       Rung comments in program logic

  Unique Base Names     8,796         After stripping :I, :O, :C, :S, :I1,
                                      :O1 suffixes
  --------------------- ------------- ------------------------------------

**5.2 IO List Structure**

  ---------------------- ------------------------------------------------
  **Metric**             **Value**

  Total Data Rows        3,866 (excluding headers)

  Active Device Points   3,261

  Spare Points           569

  Unique IO Tags         3,243

  Unique Device Tags     1,516

  Panels                 X1, X2, X3, X4, X5, X6, X7

  Module Types           AI, AO, DI, DO, RTD, TTL Input, Fiber

  Address Formats        PLC5 (254 pts), CLX (3,007 pts)
  ---------------------- ------------------------------------------------

**5.3 Rack Infrastructure**

  ----------- --------------------- --------------- ---------------------------
  **Panel**   **Racks**             **Type**        **Location**

  X0          \-\--                 ControlLogix    Truck Loading 2nd Floor
                                    (processor)     (MCC Room)

  X1          0, 1, 2, 3            PLC5            Truck Loading 2nd Floor
                                                    (MCC Room)

  X2          4, 5, 6, 7            PLC5            Deodorizer MCC Room on East
                                                    Wall

  X3          10, 11, 12            PLC5            Lauric Tank Farm

  X4          14--15, 16--17,       PLC5            Truck Loading Ground Level
              20--21, 22--23                        

  X5          24                    ControlLogix    Additive Building Ground
                                                    Level

  X6          25                    ControlLogix    Additive Building 2nd Level

  X7          26                    ControlLogix    Additive Building Ground
                                                    Level
  ----------- --------------------- --------------- ---------------------------

**5.4 Key Data Quality Observations**

1.  **Case inconsistency:** IO List uses \"Rack0:I.Data\[5\].0\" while
    PLC uses \"Rack0:I.DATA\[5\].0\". Case-insensitive matching is
    mandatory.

2.  **Suffix divergence:** IO List tags include IO-type suffixes
    (\"TSV22_EV\", \"P611_MC\", \"AS611_AUX\") while PLC comments use
    base names only (\"TSV22\", \"P611\", \"AS611\"). Suffix stripping
    is essential.

3.  **Comment coverage gaps:** Only 113 of 3,007 CLX IO points have PLC
    COMMENT entries. This means most points can only be verified at the
    rack level, not the individual bit/channel level.

4.  **Device name conflicts:** Some addresses where comments DO exist
    show different device names (IO List: \"FT656B_Pulse\" vs PLC
    comment: \"HLSTL5C\" at Rack0:I.DATA\[5\].6). These must be flagged
    as conflicts for human review.

5.  **ENet-only devices:** 142 EtherNet/IP module tags (E300, VFD,
    IPDev) exist in the PLC with no IO List counterpart. This is
    expected---they represent devices communicating over Ethernet that
    don't occupy traditional rack IO slots.

6.  **Program-only tags:** 7,255+ tags are program-level working memory
    (DINT, REAL, BOOL, TIMER, etc.) with no physical IO mapping. These
    must be excluded from IO verification.

**6. Functional Requirements**

**6.1 Input Requirements**

  ---------- ------------------------------------------------ --------------
  **ID**     **Requirement**                                  **Priority**

  FR-IN-01   Accept RSLogix 5000 CSV tag export files (TAG,   Must Have
             COMMENT, ALIAS, RCOMMENT records)                

  FR-IN-02   Accept IO List XLSX files with configurable      Must Have
             column mapping (panel, rack, group, slot,        
             channel, address, IO tag, device tag, module     
             type)                                            

  FR-IN-03   Parse the Index sheet to identify rack types     Must Have
             (PLC5 vs ControlLogix) and physical locations    

  FR-IN-04   Parse the Rack Layouts sheet for physical        Should Have
             slot-to-device cross-reference data              

  FR-IN-05   Support L5X file format as an alternative PLC    Should Have
             data source (richer structured XML)              

  FR-IN-06   Validate input files on load: detect encoding    Must Have
             issues, verify expected columns/headers, report  
             row counts                                       

  FR-IN-07   Handle non-UTF-8 encodings (the CHRL tag export  Must Have
             uses Latin-1 with degree symbols)                
  ---------- ------------------------------------------------ --------------

**6.2 Processing Requirements**

  ---------- ------------------------------------------------ --------------
  **ID**     **Requirement**                                  **Priority**

  FR-PR-01   Execute matching strategies in defined cascade   Must Have
             order (Section 4)                                

  FR-PR-02   Classify every device into exactly one of: PLC   Must Have
             Only, IO List Only, Both, Both (Rack Only),      
             Conflict                                         

  FR-PR-03   Apply tag normalization rules: case-folding,     Must Have
             suffix stripping per configurable suffix list    

  FR-PR-04   Apply address normalization: unify PLC5 and CLX  Must Have
             address formats for comparison                   

  FR-PR-05   Identify and correctly exclude spare points from Must Have
             mismatch reporting                               

  FR-PR-06   Identify and correctly classify program-only     Must Have
             tags (working memory, UDTs, SFCs) as non-IO      

  FR-PR-07   Detect and flag naming conflicts where address   Must Have
             matches but device names differ                  

  FR-PR-08   Support configurable matching rules (add/remove  Should Have
             suffixes, add prefix patterns, define new        
             strategies)                                      

  FR-PR-09   Process the full CHRL dataset (29,000+ CSV       Must Have
             lines, 3,800+ XLSX rows) in under 30 seconds     
  ---------- ------------------------------------------------ --------------

**6.3 Output Requirements**

  ----------- ----------------------------------------------- --------------
  **ID**      **Requirement**                                 **Priority**

  FR-OUT-01   Generate a master verification report with one  Must Have
              row per IO device showing: device tag, IO tag,  
              PLC address, classification (PLC Only / IO List 
              Only / Both / Conflict), matching strategy      
              used, confidence level, and any flags           

  FR-OUT-02   Generate a summary dashboard: total counts per  Must Have
              classification, coverage percentages, gap       
              analysis by panel/rack                          

  FR-OUT-03   Generate a conflict report listing all cases    Must Have
              where device name mismatches were detected at   
              matching addresses                              

  FR-OUT-04   Export verification report as XLSX with         Must Have
              conditional formatting (green = Both, yellow =  
              Rack Only, red = IO List Only, blue = PLC Only, 
              orange = Conflict)                              

  FR-OUT-05   Export verification report as HTML with         Should Have
              interactive filtering, sorting, and search      

  FR-OUT-06   Include full audit trail per device: which      Must Have
              rules were evaluated, what data was compared,   
              why a match was or wasn't declared              

  FR-OUT-07   Generate a coverage heatmap by panel and rack   Should Have
              showing verification status distribution        
  ----------- ----------------------------------------------- --------------

**6.4 Accuracy & Auditability Requirements**

  ----------- ----------------------------------------------- --------------
  **ID**      **Requirement**                                 **Priority**

  FR-ACC-01   Zero tolerance for false positives: a device    Must Have
              must never be classified as \"Both\" unless an  
              unambiguous match exists                        

  FR-ACC-02   Zero tolerance for false negatives: a device    Must Have
              must never be classified as \"IO List Only\" if 
              it demonstrably exists in the PLC data          

  FR-ACC-03   Every classification must be independently      Must Have
              verifiable: an engineer can trace back to the   
              exact CSV line and XLSX row that produced the   
              result                                          

  FR-ACC-04   Provide a \"verification proof\" for each       Must Have
              match: the specific PLC TAG/COMMENT record, the 
              specific IO List row, and the normalization     
              steps applied                                   

  FR-ACC-05   Support re-execution with identical results     Must Have
              given the same inputs (fully deterministic)     

  FR-ACC-06   Support manual override: an engineer can mark a Should Have
              classification as reviewed/approved/corrected   
              with their name and timestamp                   
  ----------- ----------------------------------------------- --------------

**7. Non-Functional Requirements**

  --------------- ---------------------------------------------------------
  **Category**    **Requirement**

  Performance     Complete full analysis of CHRL-scale datasets in under 30
                  seconds on standard hardware

  Portability     Run as a standalone desktop application or CLI tool; no
                  cloud dependency required

  Security        All data processing is local; no project data leaves the
                  workstation

  Extensibility   Matching strategies are modular; new rules can be added
                  without modifying existing ones

  Testability     Each matching strategy has independent unit tests with
                  known-good test vectors

  Documentation   All matching rules are documented with examples; the tool
                  is self-documenting via audit logs

  Usability       Non-programmer automation engineers can run the tool by
                  pointing it at two files and clicking a button
  --------------- ---------------------------------------------------------

**8. Technical Implementation Guidance**

**8.1 Recommended Technology Stack**

  --------------- --------------------- ------------------------------------
  **Component**   **Recommendation**    **Rationale**

  Language        Python 3.10+          Excellent CSV/XLSX parsing
                                        libraries, rapid development,
                                        familiar to automation engineers

  CSV Parsing     Custom line-by-line   RSLogix CSV is non-standard (mixed
                  parser                record types, multi-line
                                        descriptions); csv.reader
                                        insufficient

  XLSX Parsing    openpyxl              Handles large Excel files with
                                        formulas, merged cells, and multiple
                                        sheets

  Normalization   Regex-based rule      Configurable pattern matching for
                  engine                tag name and address normalization

  Output (XLSX)   openpyxl with         Native Excel output with
                  conditional           professional formatting
                  formatting            

  Output (HTML)   Jinja2 templates +    Interactive filtering and sorting
                  DataTables.js         without backend

  GUI (optional)  Streamlit or PyQt     Rapid web-based or desktop UI for
                                        non-programmers

  Testing         pytest with           Test each strategy independently
                  parameterized         with real data samples
                  fixtures              
  --------------- --------------------- ------------------------------------

**8.2 Data Model**

The core data model consists of three primary entities that are
reconciled by the matching engine:

  ------------- ------------------------------ ----------------------------
  **Entity**    **Key Fields**                 **Source**

  PLCTag        type, name, base_name,         CSV TAG, COMMENT, ALIAS
                description, datatype, scope,  lines
                specifier, suffixes\[\],       
                category (IO_Module \| Program 
                \| Alias)                      

  IODevice      panel, rack, group, slot,      XLSX ESCO List sheet
                channel, plc_address, io_tag,  
                device_tag, module_type,       
                module, range_low, range_high, 
                units, address_format (PLC5 \| 
                CLX)                           

  MatchResult   io_device_ref, plc_tag_ref,    Computed by matching engine
                strategy_id, confidence,       
                classification, conflict_flag, 
                audit_trail\[\], reviewer,     
                review_timestamp               
  ------------- ------------------------------ ----------------------------

**8.3 Tag Classification Logic**

PLC tags must be classified before matching to separate IO-relevant tags
from program working memory:

  --------------- ------------------------------------ -------------------
  **Category**    **Detection Rule**                   **Count (CHRL)**

  IO Module Tags  Datatype starts with AB: or EH:      314
                  (Rockwell/EtherNet module            
                  definitions)                         

  Rack IO Tags    Name matches Rack\<N\>:I or          \~50
                  Rack\<N\>:O pattern                  

  ENet Device     Name matches E300\_\*, VFD\_\*,      142
  Tags            IPDev\_\*, IPDEV\_\* prefix patterns 

  Alias Tags      Record type is ALIAS                 6,474

  Program Tags    Datatype is DINT, REAL, INT, BOOL,   7,255+
                  TIMER, COUNTER, STRING, or known UDT 

  Bit-Level       Record type is COMMENT with          2,629
  Comments        specifier pointing to specific       
                  bit/channel                          
  --------------- ------------------------------------ -------------------

**9. Testing Strategy**

Given the zero-tolerance accuracy requirement, the testing strategy is
designed to provide mathematical certainty that the matching engine
produces correct results.

**9.1 Test Levels**

  ------------- ------------------------------------- -------------------
  **Level**     **Description**                       **Coverage Target**

  Unit Tests    Each matching strategy tested         100% branch
                independently with synthetic data     coverage per
                covering all edge cases: exact        strategy
                matches, near-misses, case            
                variations, suffix combinations,      
                empty fields, unicode characters      

  Integration   End-to-end test using a curated       100% agreement with
  Tests         subset of the actual CHRL data (\~100 hand-verified data
                devices hand-verified by an engineer) 
                as ground truth                       

  Regression    Full CHRL dataset run, results        Zero unexpected
  Tests         compared against previous known-good  classification
                run to detect any changes             changes between
                                                      runs

  Adversarial   Deliberately crafted edge cases:      Zero false
  Tests         devices with names that are           positives or
                substrings of each other (LT611,      negatives
                LT6110), devices with identical names 
                in different racks, spare points with 
                device-like names                     

  Human Audit   Random sample of 10% of results       100% agreement with
                manually verified by a second         manual verification
                engineer against source documents     
  ------------- ------------------------------------- -------------------

**9.2 Specific Test Vectors (from CHRL Data)**

  --------------- ---------------------------------- -----------------------
  **Test Case**   **Input**                          **Expected Result**

  Case            IO: Rack0:I.Data\[5\].7 vs PLC:    Both --- Strategy 1
  sensitivity     Rack0:I.DATA\[5\].7 (HLSTL5A)      match

  Suffix          IO: TSV22_EV vs PLC comment: TSV22 Both --- Strategy 5
  stripping                                          match after stripping
                                                     \_EV

  Name conflict   IO: FT656B_Pulse @                 Conflict --- address
                  Rack0:I.Data\[5\].6 vs PLC         matches, name differs
                  comment: HLSTL5C @ same address    

  ENet extraction PLC: E300_P621:I vs IO Device Tag: Both --- Strategy 4
                  P621                               match

  Spare exclusion IO Tag = \"Spare\" at              Excluded from mismatch
                  Rack0_Group0_Slot0_IO.READ\[14\]   reporting

  Rack-only match IO: AS611_AUX @                    Both (Rack Only) ---
                  Rack0:I.Data\[6\].0, no PLC        Strategy 3
                  COMMENT, but Rack0:I TAG exists    

  Substring       IO: LT611 should NOT match PLC     No match --- exact base
  safety          program tag: LT6110_Monitor        name required

  PLC-only ENet   PLC: E300_P9203:I with no IO List  PLC Only --- expected
                  entry for P9203                    for ENet overload
                                                     relays
  --------------- ---------------------------------- -----------------------

**10. Risk Analysis**

  ------------------ ---------------- ------------ ------------------------------------
  **Risk**           **Likelihood**   **Impact**   **Mitigation**

  Undiscovered       Medium           High         Configurable suffix/prefix lists;
  naming convention                                human review of all \"IO List Only\"
  not covered by                                   results; iterative rule refinement
  normalization                                    
  rules                                            

  IO List contains   Medium           High         Rack Layout triangulation (Strategy
  errors (wrong                                    6) provides independent
  address, typos in                                verification; conflict detection
  device tags)                                     flags discrepancies

  PLC CSV export is  Low              Critical     Input validation checks expected row
  incomplete or                                    counts; file size sanity check;
  truncated                                        compare tag count against project
                                                   scope documentation

  New module types   Medium           Medium       Extensible module type registry;
  not handled by                                   unknown datatypes flagged for review
  classification                                   rather than silently miscategorized
  logic                                            

  Tool gives false   Medium           Critical     All \"Both (Rack Only)\" results
  confidence leading                               clearly flagged as partial matches;
  to skipped manual                                summary report highlights
  checks                                           verification gaps; tool designed as
                                                   an aid to engineering judgment, not
                                                   a replacement
  ------------------ ---------------- ------------ ------------------------------------

**11. Future Enhancements**

-   **L5X Native Parsing:** Parse the L5X project file directly for
    richer data including module configuration, connection paths, and
    rung logic references to device tags.

-   **Bidirectional Program Logic Scan:** Scan PLC rung logic to find
    every reference to each IO tag, verifying not just that the device
    exists in the PLC but that it's actually being used in control
    logic.

-   **Integration with Device Tracks:** Feed IO Crosscheck results into
    the Device Tracks lifecycle management system to automatically
    update device status from \"Defined\" to \"Verified in PLC\".

-   **Diff Mode:** Compare two runs of the tool (before/after PLC edits)
    to show what changed---new matches, lost matches, new conflicts.

-   **Multi-PLC Support:** Support projects with multiple PLC programs
    being migrated in parallel, with cross-PLC device tracking.

-   **AI-Assisted Conflict Resolution:** Use an LLM to suggest
    resolutions for naming conflicts by analyzing surrounding context
    (neighboring devices, module types, historical patterns)---always
    presented as suggestions for engineer approval, never auto-applied.

**12. Glossary**

  --------------- -------------------------------------------------------
  **Term**        **Definition**

  CLX             ControlLogix --- Rockwell Automation's
                  current-generation PLC platform

  PLC5            Rockwell's legacy PLC platform being replaced in
                  migration projects

  E300            AB E300 Electronic Overload Relay, communicating via
                  EtherNet/IP

  VFD             Variable Frequency Drive, typically PowerFlex series

  IPDev           Generic IP device communicating via EtherNet/IP (e.g.,
                  Endress+Hauser Promass flowmeters)

  IO List         Master spreadsheet documenting every physical IO point:
                  its address, device tag, module type, and signal range

  TAG (PLC)       A named data element in the ControlLogix program; can
                  represent an IO module, a working variable, or a UDT
                  instance

  COMMENT (PLC)   A descriptive annotation on a specific data element
                  within a TAG, typically used to label individual bits
                  or channels

  ALIAS (PLC)     A named reference to another tag or a specific element
                  within a tag, used for slot-level access patterns

  IO Tag          The functional identifier for an IO point (e.g., LT611
                  = Level Transmitter 611)

  Device Tag      The physical device identifier, may differ from IO tag
                  when a device has multiple IO points

  Normalization   The process of converting tag names to a canonical form
                  for comparison (case-folding, suffix stripping)

  Suffix          IO-type descriptor appended to device names (\_EV =
                  energize valve, \_MC = motor contactor, \_ZSO = zone
                  switch open, etc.)

  DXA             Device-independent pixel unit used in Office XML (1440
                  DXA = 1 inch)
  --------------- -------------------------------------------------------

*--- End of Document ---*
