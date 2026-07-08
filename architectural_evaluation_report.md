# Architectural Evaluation of Monolithic and Modular HRI Challenge Implementations

## 1. Purpose and Scope

This report evaluates two architecturally equivalent implementations of the HRI challenge behavior from the perspective of software architecture evolution. The objective is not to evaluate runtime performance or infer abstract graph quality, but to measure concrete architectural evidence that can be checked in the repository: executable BT size, capability granularity, duplicated capability implementations, coordination artifacts, and the artifacts affected by representative evolution scenarios.

The properties evaluated are:

| Property | Operational Definition Used in This Report |
|---|---|
| Modularity | Degree to which each functional capability is represented by an independent executable BT/module artifact |
| Localization of change | Number and size of artifacts that must be edited for an evolution scenario |
| Explicit coordination | Whether sequencing and recovery are represented as separate coordination artifacts rather than embedded in capability logic |
| Reusable capabilities | Whether a capability implementation is written once and reused by flow configuration, or duplicated inline |

The evaluation compares:

| Architecture | Main executable behavior artifact(s) in this evaluation | Coordination mechanism measured in this evaluation |
|---|---|---|
| Monolithic BT | `bt_xml/hri_challenge.xml` | Inline BT sequencing |
| Modular architecture | Per-capability BT XMLs and Cognitive Modules | `HRIChallengeMaster.cpp` and `config/params.yaml` flows |

## 2. Evaluation Scenarios

The static evaluation is organized around three representative evolution scenarios.

| ID | Scenario | Architectural Concern |
|---|---|---|
| S1 | Add environmental sound awareness / doorbell detection | Capability extension |
| S2 | Replace the seating guidance strategy | Capability replacement |
| S3 | Manipulation unavailable or degraded | Capability degradation |

## 3. Measurement Methodology

### 3.1 Static BT Metrics

BT metrics were extracted from XML artifacts by counting executable XML elements.

| Metric reported in BT tables | Scope and definition |
|---|---|
| Executable BT artifact size, in nodes | Number of executable XML nodes in one named BT XML artifact, excluding `<root>` and `<BehaviorTree>` |
| Action-node count within the named BT artifact | Nodes with XML tag `Action` inside that BT artifact |
| Condition-node count within the named BT artifact | Nodes with XML tag `Condition` inside that BT artifact |
| Control/decorator-node count within the named BT artifact | Control or decorator nodes such as `Sequence`, `Fallback`, `RetryUntilSuccessful`, `Timeout`, `Delay`, `ReactiveSequence`, etc. inside that BT artifact |
| Maximum XML nesting depth within the named BT artifact | Maximum XML nesting depth inside the executable tree of that BT artifact |
| Distinct blackboard variables within the named BT artifact | Distinct `{variable}` placeholders appearing in XML attributes of that BT artifact |

Blackboard-variable count is interpreted as a static estimate of shared-state surface area. It is not interpreted as a precise runtime data-flow graph unless a producer-consumer relation can be inferred from capability semantics and BT usage.

### 3.2 Capability and Coordination Evidence

The analysis reports capability evidence at the level of executable BTs, Cognitive Module source files, and flow configuration. It does not use graph density, node degree, or fan-in/fan-out as primary architectural metrics because those values depend strongly on graph construction choices and do not directly identify which software artifacts must be understood or changed.

The capabilities considered are:

| Functional capability | Number of inline implementations inside full monolithic BT `hri_challenge.xml` | Modular executable capability artifact(s) |
|---|---:|---|
| Greeting | 2 | `greeting_guest.xml` / `GreetingGuestCM.cpp` |
| Describe / Invite | 2 | `describe_person.xml` / `DescribePersonCM.cpp` |
| Introduce Guest | 2 | `introduce_guest.xml` / `IntroduceGuestCM.cpp` |
| Find Seat | 2 | `find_seat.xml` / `FindSeatCM.cpp` |
| Grab Bag | 1 | `grab_bag.xml` / `GrabBagCM.cpp` |
| Transport Bag | 1 | `transport_bag.xml` / `TransportBagCM.cpp` |
| Recovery | Embedded fallback/retry behavior | `recovery.xml` / `RecoveryCM.cpp` |

Two forms of architectural evidence are separated.

#### Control-flow evidence

Control-flow evidence identifies where the execution order of capabilities is encoded.

| Architecture | Artifact scope used for execution-order evidence |
|---|---|
| Monolithic | Sequential ordering of capability sections inside `hri_challenge.xml` |
| Modular | Explicit flow order in `config/params.yaml` |

#### Data/interface evidence

Data/interface evidence is reported only when one capability produces information that another capability consumes. Simple reuse of common parameter names such as `cam_frame`, `h_name`, or `attention_home` is not counted as a capability dependency, because those values are configuration context rather than capability output.

Producer-consumer relations used in this report:

| Producer capability artifact scope | Produced information | Consumer capability artifact scope | Artifact evidence for this interface relation |
|---|---|---|---|
| Greeting capability (`greeting_guest.xml`) | Guest name, drink, description, identity/facts | Introduce Guest capability (`introduce_guest.xml`) | `StoreGuestInfo` in `greeting_guest.xml`; `GetGuestInfo` in `introduce_guest.xml` |
| Greeting capability (`greeting_guest.xml`) | Guest identity / current attended guest | Find Seat capability (`find_seat.xml`) | `GetAttendedGuest` and guest index usage in `find_seat.xml` |
| Greeting capability (`greeting_guest.xml`) | Guest identity / current attended guest | Describe / Invite capability (`describe_person.xml`) | Shared attended-guest state and guest progression |
| Grab Bag capability (`grab_bag.xml`) | Physical bag secured by robot | Transport Bag capability (`transport_bag.xml`) | Bag handover precedes `transport_bag.xml` in bag flow |
| Find Seat capability (`find_seat.xml`) | Guest seated / seating objective complete | Transport Bag capability (`transport_bag.xml`) | Bag transport occurs after seating in flow |
| Recovery capability (`recovery.xml`) | Continue/stop decision | Master coordination (`HRIChallengeMaster.cpp`) | `recovery_cognitive_module` completion handled in `HRIChallengeMaster.cpp` |

These producer-consumer relations are used qualitatively to identify interface coupling. They are not converted into graph-degree metrics because the contribution of the paper concerns architectural localization of executable behavior and modifications, not abstract graph topology.

### 3.3 Modification Impact Metrics

For S1-S3, modification impact is reported only from implemented BT XML variants. The following metrics are computed from the original and final XML artifacts:

| Scenario metric reported in S1-S3 tables | Scope and definition |
|---|---|
| Implemented BT XML artifact(s) | Concrete generated XML file(s) used for the scenario measurement |
| Edited BT artifact size, nodes | Executable node count of the baseline BT XML artifact before the implemented change; 0 for a newly generated BT artifact |
| Final BT artifact size after implemented change, nodes | Executable node count of the generated scenario BT XML artifact after the implemented change |
| Added executable BT nodes, count | Executable XML nodes inserted by the implemented change |
| Removed executable BT nodes, count | Executable XML nodes deleted by the implemented change |
| Modified execution locations, count | Number of concrete behavior locations changed in the implemented BT XML artifact(s) |
| Affected fallback/retry/recovery nodes, count | Changed executable nodes with tag `Fallback`, `ReactiveFallback`, or `RetryUntilSuccessful` |
| Affected control/decorator nodes, count | Changed executable control/decorator nodes in the inserted or deleted subtrees |

Coordination/configuration artifacts such as flow YAML, launch files, build files, plugin registration, and Cognitive Module source files are discussed as architectural context but are not counted in S1-S3 modification metrics unless they are implemented as part of the measured artifact set.

### 3.4 Reproducible Scenario Implementation Metrics

S1-S3 modification metrics are computed from implemented BT XML variants rather than estimated from the original artifacts. The monolithic variants are generated as `/tmp/hri_s1.xml`, `/tmp/hri_s2.xml`, and `/tmp/hri_s3.xml`. Modular comparison variants are generated as `/tmp/doorbell_detection_s1.xml`, `/tmp/find_seat_s2.xml`, `/tmp/grab_bag_s3.xml`, and `/tmp/transport_bag_s3.xml`.

The reported node counts are produced automatically from the original and final BT XML artifacts. `Final BT artifact size after implemented change` is the executable node count of the actual generated scenario BT. `Added BT nodes` and `removed BT nodes` are supporting metrics that count executable XML nodes in the concrete inserted or deleted subtrees. `Existing nodes with attribute or tag changes` counts retained executable nodes whose XML tag or attributes are changed in place. `Affected fallback/retry/recovery nodes` counts changed executable nodes with tag `Fallback`, `ReactiveFallback`, or `RetryUntilSuccessful`. These values are BT-XML modification metrics only; non-BT integration work is not counted unless it is implemented in the measured artifacts.

## 4. Structural Results

### 4.1 System-Level Executable BT Size and Capability Granularity

| System-level architectural metric | Monolithic implementation scope and value | Modular implementation scope and value |
|---|---|---|
| Count of executable BT artifacts in the evaluated system | 1 full-task BT artifact | 7 capability BT artifacts |
| Count of Cognitive Module executables in the evaluated system | 0 | 7 capability module executables |
| Largest executable BT artifact size in the evaluated system | 599 nodes in `hri_challenge.xml` | 176 nodes in `greeting_guest.xml` |
| Average executable BT artifact size across evaluated BT artifacts | 599.0 nodes across 1 full-task BT | 49.4 nodes across 7 capability BTs |
| Median executable BT artifact size across evaluated BT artifacts | 599 nodes across 1 full-task BT | 40 nodes across 7 capability BTs |
| Total BT nodes | 599 nodes encoded in the full monolithic BT XML artifact | 346 nodes encoded across all 7 evaluated modular capability BT XML artifacts |
| Count of explicit flow definitions in coordination configuration | 0 | 2 flows in `config/params.yaml` |
| Count of explicit recovery capability modules | 0 | 1 (`recovery_cognitive_module`) |

This measurement supports only the following claim: the modular architecture distributes behavior across smaller executable BT artifacts, while the monolithic architecture concentrates the complete behavior in one 599-node BT.

Note: the monolithic values describe the single full-task BT artifact. The modular values describe the set of seven evaluated capability BT artifacts; the modular total is not a single executable BT size.

Methodological note on `Total BT nodes`: this metric measures the amount of behavior encoded inside BT XML artifacts. It is not a measure of total software complexity. In the modular implementation, part of the behavior organization is intentionally externalized to lifecycle management, flow configuration, launch files, and coordination artifacts; those non-BT artifacts are not counted by `Total BT nodes`.

### 4.2 Per-Capability Modular BT Structural Complexity

| Modular capability BT artifact | Executable BT artifact size, nodes | Action nodes in this BT | Condition nodes in this BT | Control/decorator nodes in this BT | Maximum XML depth in this BT | Distinct blackboard variables in this BT |
|---|---:|---:|---:|---:|---:|---:|
| Greeting | 176 | 63 | 14 | 96 | 12 | 15 |
| Describe / Invite | 7 | 6 | 0 | 1 | 3 | 6 |
| Introduce Guest | 42 | 27 | 3 | 12 | 8 | 14 |
| Find Seat | 24 | 14 | 1 | 9 | 8 | 9 |
| Grab Bag | 54 | 26 | 5 | 23 | 9 | 11 |
| Transport Bag | 40 | 23 | 4 | 13 | 8 | 9 |
| Recovery | 3 | 2 | 0 | 1 | 3 | 0 |

Note: each row reports metrics for one modular capability BT XML artifact only. These rows are not system totals.

### 4.3 Duplicated Capability Implementations

| Functional capability | Inline implementations inside full monolithic BT `hri_challenge.xml` | Modular capability implementations in evaluated modular system | Difference in implementation count |
|---|---:|---:|---:|
| Greeting | 2 | 1 | +1 duplicated in monolithic |
| Describe / Invite | 2 | 1 | +1 duplicated in monolithic |
| Introduce Guest | 2 | 1 | +1 duplicated in monolithic |
| Find Seat | 2 | 1 | +1 duplicated in monolithic |
| Grab Bag | 1 | 1 | 0 |
| Transport Bag | 1 | 1 | 0 |
| Recovery | Embedded many times | 1 explicit module | Different representation |

Total duplicated capability implementations in the monolithic BT: 4 additional inline capability sections relative to the modular architecture.

## 5. Execution Order Evidence

### 5.1 Monolithic Execution Order

The monolithic BT encodes the intended task as one inline sequence:

```text
Greeting1 -> Describe1 -> MoveToParty1 -> Introduce1 -> FindSeat1 -> ReturnDoor
          -> Greeting2 -> GrabBag2 -> Describe2 -> MoveToParty2 -> Introduce2
          -> FindSeat2 -> TransportBag2
```

| Monolithic execution-order metric scoped to full `hri_challenge.xml` | Measured value within `hri_challenge.xml` |
|---|---:|
| Functional capability instances encoded inside the full monolithic BT | 13 |
| Sequential transitions between capability instances inside the full monolithic BT | 12 |
| Execution locations containing duplicated reusable capability implementations inside the full monolithic BT | 8 |

### 5.2 Modular Execution Order

Configured flows from `config/params.yaml`:

| Flow definition in `config/params.yaml` | Capability sequence encoded by that flow |
|---|---|
| `flow_1` | Greeting -> Find Seat -> Describe / Invite |
| `flow_2` | Greeting -> Grab Bag -> Introduce Guest -> Find Seat -> Transport Bag |

Unique capability transitions represented in flow configuration:

| Unique configured capability transition in `config/params.yaml` |
|---|
| Greeting -> Find Seat |
| Find Seat -> Describe / Invite |
| Greeting -> Grab Bag |
| Grab Bag -> Introduce Guest |
| Introduce Guest -> Find Seat |
| Find Seat -> Transport Bag |

| Modular execution-order metric scoped to `config/params.yaml` flow definitions | Measured value within evaluated flow definitions |
|---|---:|
| Unique functional capability implementations referenced by the evaluated flows | 6 |
| Unique configured capability transitions across the evaluated flows | 6 |
| Capability implementations reused by more than one evaluated flow | Greeting, Find Seat |

This section is limited to where execution order is represented. It does not rank capabilities by graph degree because that would not add evidence about executable artifact size, duplicated implementations, or change localization.

## 6. Data and Interface Evidence Between Functional Capabilities

### 6.1 Producer-Consumer Relations

| Producer capability artifact scope | Consumer capability artifact scope | Produced/consumed information | Artifact evidence for this interface relation |
|---|---|---|---|
| Greeting capability (`greeting_guest.xml`) | Introduce Guest capability (`introduce_guest.xml`) | Guest facts | `StoreGuestInfo` -> `GetGuestInfo` |
| Greeting capability (`greeting_guest.xml`) | Find Seat capability (`find_seat.xml`) | Attended guest identity / guest index | `GetAttendedGuest`, `RemoveStringPrefix` |
| Greeting capability (`greeting_guest.xml`) | Describe / Invite capability (`describe_person.xml`) | Current guest progression | `GetAttendedGuest`, guest index variables |
| Grab Bag capability (`grab_bag.xml`) | Transport Bag capability (`transport_bag.xml`) | Physical possession of bag | `grab_bag.xml` precedes `transport_bag.xml` in bag flow |
| Find Seat capability (`find_seat.xml`) | Transport Bag capability (`transport_bag.xml`) | Seating completion before bag delivery | Bag transport occurs after seating in flow |
| Recovery capability (`recovery.xml`) | Master coordination (`HRIChallengeMaster.cpp`) | Continue/stop decision | `handle_recovery_completion()` in `HRIChallengeMaster.cpp` |

This table intentionally excludes generic parameter sharing. For example, `cam_frame` and `attention_home` are not counted as producer-consumer relations because they are configuration inputs used by multiple capabilities, not outputs of one capability consumed by another. The table is retained to document interface coupling that can affect modification scenarios; it is not used to compute graph fan-in, fan-out, or density.

## 7. Explicit Coordination Artifacts

| Coordination concern | Monolithic implementation artifact scope | Modular implementation artifact scope |
|---|---|---|
| Capability order | Inline in `hri_challenge.xml` | `config/params.yaml` flow lists |
| Capability activation | Single BT tick loop | Lifecycle activation by `HRIChallengeMaster.cpp` |
| Completion signal | BT return status only | Per-module `/completion` topics |
| Status reporting | BT execution state inside one runner | Per-module `bt_status` outputs |
| Recovery policy | Embedded fallback/retry nodes | `recovery_cognitive_module` and master retry policy |
| Capability executable boundary | None inside BT | One executable per Cognitive Module |

The modular architecture has more coordination artifacts, but those artifacts explicitly encode flow order, lifecycle state, completion, and recovery. The monolithic architecture encodes capability order directly in one BT artifact.

## 8. Scenario S1: Environmental Sound Awareness / Doorbell Detection

### 8.1 Change Model

Add a doorbell or environmental sound-awareness capability before guest reception. The measured change model treats doorbell detection as a new capability. In the monolithic implementation, the new behavior is inserted inline at each guest-reception entry point. In the modular implementation, the new behavior is added as a new Cognitive Module and inserted into flow configuration.

### 8.2 Implemented BT Artifacts

| S1 implemented BT artifact | Architecture | Relationship to baseline BT artifacts | Implemented change |
|---|---|---|---|
| `/tmp/hri_s1.xml` | Monolithic | Modified copy of the 599-node `hri_challenge.xml` full-task BT | Inserts doorbell-detection behavior before both guest reception locations |
| `/tmp/doorbell_detection_s1.xml` | Modular | New capability BT artifact | Encodes doorbell-detection behavior as a standalone capability BT |

### 8.3 Automatically Computed BT-XML Modification Metrics

| S1 BT-XML metric computed from implemented artifacts | Monolithic value from `/tmp/hri_s1.xml` | Modular value from `/tmp/doorbell_detection_s1.xml` |
|---|---:|---:|
| Edited BT artifact size, nodes | 599 | 0; new BT artifact |
| Final BT artifact size after implemented change, nodes | 613 | 8 |
| Added executable BT nodes, count | 14 | 8 |
| Removed executable BT nodes, count | 0 | 0 |
| Modified execution locations, count | 2 | 1 |
| Affected fallback/retry/recovery nodes, count | 4 | 2 |
| Affected control/decorator nodes, count | 6 | 3 |

Note: the S1 monolithic metric is computed from two concrete insertions into `/tmp/hri_s1.xml`. The S1 modular metric is computed from the generated standalone BT `/tmp/doorbell_detection_s1.xml`; flow, launch, build, and Cognitive Module integration are not counted in this BT-XML metric table because they are not BT XML nodes.

Evidence-supported interpretation: in the implemented BT XML changes, the monolithic variant adds 14 executable nodes across two existing reception execution locations in the full-task BT. The modular variant adds an 8-node standalone doorbell BT and does not edit any existing modular capability BT artifact.

## 9. Scenario S2: Replace Seating Guidance Strategy

### 9.1 Change Model

Replace the strategy for finding and guiding the guest to a seat while preserving the same functional objective. The measured change model assumes the replacement can be expressed with the currently available BT action interface; therefore, no new plugin source or plugin-list change is counted.

### 9.2 Implemented BT Artifacts

| S2 implemented BT artifact | Architecture | Relationship to baseline BT artifacts | Implemented change |
|---|---|---|---|
| `/tmp/hri_s2.xml` | Monolithic | Modified copy of the 599-node `hri_challenge.xml` full-task BT | Replaces both inline Find Seat guidance sections |
| `/tmp/find_seat_s2.xml` | Modular | Modified copy of the 24-node `find_seat.xml` capability BT | Replaces the reusable Find Seat guidance section |

### 9.3 Automatically Computed BT-XML Modification Metrics

| S2 BT-XML metric computed from implemented artifacts | Monolithic value from `/tmp/hri_s2.xml` | Modular value from `/tmp/find_seat_s2.xml` |
|---|---:|---:|
| Edited BT artifact size, nodes | 599 | 24 |
| Final BT artifact size after implemented change, nodes | 597 | 23 |
| Added executable BT nodes, count | 8 | 4 |
| Removed executable BT nodes, count | 10 | 5 |
| Modified execution locations, count | 2 | 1 |
| Affected fallback/retry/recovery nodes, count | 2 | 1 |
| Affected control/decorator nodes, count | 6 | 3 |

Note: the S2 monolithic metric is computed from two implemented replacements in `/tmp/hri_s2.xml`; the modular metric is computed from one implemented replacement in `/tmp/find_seat_s2.xml`. The modular value of 24 original nodes is the size of the edited `find_seat.xml` capability BT, not the sum or average of modular BTs.

Evidence-supported interpretation: the implemented seating replacement changes two execution locations in the monolithic BT and one execution location in the modular capability BT. The edited monolithic artifact is the full 599-node BT, while the edited modular artifact is the 24-node Find Seat BT.

## 10. Scenario S3: Manipulation Unavailable or Degraded

### 10.1 Change Model

Disable or degrade arm/gripper manipulation by replacing physical bag acquisition and delivery with non-manipulation behavior inside the existing bag-related capabilities. The measured change model keeps the same high-level flow and does not remove the bag capabilities from `params.yaml`.

### 10.2 Implemented BT Artifacts

| S3 implemented BT artifact | Architecture | Relationship to baseline BT artifacts | Implemented change |
|---|---|---|---|
| `/tmp/hri_s3.xml` | Monolithic | Modified copy of the 599-node `hri_challenge.xml` full-task BT | Replaces inline `GrabBag2` handover and `TransportBag2` release manipulation with verbal-assistance behavior |
| `/tmp/grab_bag_s3.xml` | Modular | Modified copy of the 54-node `grab_bag.xml` capability BT | Replaces bag acquisition manipulation with verbal-assistance behavior |
| `/tmp/transport_bag_s3.xml` | Modular | Modified copy of the 40-node `transport_bag.xml` capability BT | Replaces bag release manipulation with verbal-assistance behavior |

### 10.3 Automatically Computed BT-XML Modification Metrics

| S3 BT-XML metric computed from implemented artifacts | Monolithic value from `/tmp/hri_s3.xml` | Modular value from `/tmp/grab_bag_s3.xml` and `/tmp/transport_bag_s3.xml` |
|---|---:|---:|
| Edited BT artifact size, nodes | 599 | 94 total across 54-node `grab_bag.xml` and 40-node `transport_bag.xml` |
| Final BT artifact size after implemented change, nodes | 564 | 59 total across final `grab_bag_s3.xml` and `transport_bag_s3.xml` |
| Added executable BT nodes, count | 5 | 5 |
| Removed executable BT nodes, count | 40 | 40 |
| Modified execution locations, count | 2 | 2 |
| Affected fallback/retry/recovery nodes, count | 3 | 3 |
| Affected control/decorator nodes, count | 13 | 13 |

Note: S3 keeps the same high-level flow in both implemented variants. The modular comparison reports the sum across the two edited capability BT artifacts because both `grab_bag.xml` and `transport_bag.xml` are modified by the implemented degradation.

Manipulation-related BT node IDs present in the monolithic BT include:

| Node ID | Role |
|---|---|
| `PlayMotionPredefined` | Arm/gripper posture |
| `MoveJoint` | Joint movement |
| `MoveAlongAxis` | Base/torso alignment during handover/following |
| `SetTorsoHeight` | Torso movement |
| `ExtractHandoverAlignment` | Handover pose extraction |

Evidence-supported interpretation: the implemented S3 BT changes use the same supporting edit operations in both variants: 5 executable nodes added and 40 executable nodes removed. The final monolithic BT has 564 nodes, while the final modular edited BT artifacts have 59 nodes in total. The architectural difference is the scope of the edited BT artifact(s): one 599-node monolithic BT versus two modular capability BTs whose original sizes sum to 94 nodes.

## 11. Cross-Scenario Modification Summary

| Scenario and architecture | Implemented BT XML artifact(s) | Original BT size, nodes | Final BT size after implemented change, nodes | Added BT nodes | Removed BT nodes | Existing nodes changed in place | Modified execution locations | Affected fallback/retry/recovery nodes |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| S1 Doorbell, monolithic | `/tmp/hri_s1.xml` | 599 | 613 | 14 | 0 | 0 | 2 | 4 |
| S1 Doorbell, modular | `/tmp/doorbell_detection_s1.xml` | 0 | 8 | 8 | 0 | 0 | 1 | 2 |
| S2 Seating, monolithic | `/tmp/hri_s2.xml` | 599 | 597 | 8 | 10 | 0 | 2 | 2 |
| S2 Seating, modular | `/tmp/find_seat_s2.xml` | 24 | 23 | 4 | 5 | 0 | 1 | 1 |
| S3 Manipulation, monolithic | `/tmp/hri_s3.xml` | 599 | 564 | 5 | 40 | 0 | 2 | 3 |
| S3 Manipulation, modular | `/tmp/grab_bag_s3.xml`; `/tmp/transport_bag_s3.xml` | 94 | 59 | 5 | 40 | 0 | 2 | 3 |

Note: this summary is restricted to implemented BT XML artifacts. It does not estimate flow, launch, build, plugin-registration, or Cognitive Module source changes that were not implemented in the measured BT XML variants.

## 12. Results Directly Supported by Measurements

| Claim | Direct supporting measurement with scope |
|---|---|
| The monolithic implementation concentrates evaluated behavior in one executable artifact | Largest executable BT artifact in evaluated monolithic system = 599-node `hri_challenge.xml`; average across evaluated monolithic BT artifacts = 599.0 nodes |
| The modular implementation distributes evaluated behavior into smaller executable capability artifacts | Largest executable BT artifact in evaluated modular system = 176-node `greeting_guest.xml`; average across 7 evaluated modular capability BT artifacts = 49.4 nodes |
| The monolithic implementation duplicates reusable capability implementations inside the full monolithic BT | Greeting, Describe / Invite, Introduce Guest, and Find Seat each occur twice inline in `hri_challenge.xml` |
| S1 doorbell extension changes fewer BT nodes in the modular implementation | Implemented S1 adds 8 BT nodes in `/tmp/doorbell_detection_s1.xml` vs 14 BT nodes in `/tmp/hri_s1.xml` |
| S2 seating replacement has smaller edited BT artifact scope in the modular architecture | Implemented S2 edits a 24-node `find_seat.xml` derivative vs the 599-node `hri_challenge.xml` derivative |
| S2 seating replacement changes fewer execution locations in the modular architecture | Implemented S2 changes 1 modular execution location vs 2 monolithic inline seating locations |
| S3 manipulation degradation has smaller edited BT artifact scope in the modular architecture | Implemented S3 edits modular BTs totaling 94 original nodes vs the 599-node monolithic BT |
| S3 manipulation degradation has the same added/removed BT-node support metrics in both implementations under the implemented change | Implemented S3 adds 5 BT nodes and removes 40 BT nodes in both variants; final BT size is 564 nodes for `/tmp/hri_s3.xml` and 59 nodes across `/tmp/grab_bag_s3.xml` and `/tmp/transport_bag_s3.xml` |
| Modular coordination is explicit in artifacts | `params.yaml` flows, per-module completion topics, lifecycle management in `HRIChallengeMaster.cpp`, `recovery_cognitive_module` |

## 13. Conclusions

The reported measurements support a bounded architectural conclusion: the two implementations differ primarily in executable behavior granularity and in where coordination is encoded.

The monolithic implementation concentrates the complete HRI challenge behavior in one 599-node executable BT artifact, `hri_challenge.xml`. Four reusable capabilities appear twice inline: Greeting, Describe / Invite, Introduce Guest, and Find Seat. In the implemented S2 seating-change variant, the change is applied at two inline seating locations in `/tmp/hri_s2.xml`, which is derived from the full 599-node monolithic BT.

The modular implementation separates the behavior into seven executable capability BTs and seven Cognitive Modules. The largest executable BT artifact in the evaluated modular system is the 176-node `greeting_guest.xml`, and the average size across the seven evaluated modular capability BT artifacts is 49.4 nodes. In the implemented S2 variant, the seating strategy is edited in `/tmp/find_seat_s2.xml`, derived from the 24-node `find_seat.xml` BT. In the implemented S3 variant, manipulation degradation is edited in `/tmp/grab_bag_s3.xml` and `/tmp/transport_bag_s3.xml`, derived from BT artifacts totaling 94 original nodes, rather than inside the 599-node monolithic BT.

The implemented S1 BT-XML changes show different localization. The monolithic variant inserts doorbell behavior at two existing reception locations and adds 14 executable BT nodes to produce `/tmp/hri_s1.xml`. The modular variant encodes doorbell behavior as one new standalone BT with 8 executable nodes in `/tmp/doorbell_detection_s1.xml`; it does not edit an existing modular capability BT in the measured BT-XML artifact set.

The coordination evidence is explicit rather than inferred from graph metrics. The monolithic implementation encodes ordering inline in `hri_challenge.xml`. The modular implementation encodes flow order in `config/params.yaml`, lifecycle/completion handling in `HRIChallengeMaster.cpp`, launch participation in `launch/hri_challenge.launch.py`, and recovery as a separate `recovery_cognitive_module`. These artifacts make coordination visible, but they also become part of the modification surface when adding new capabilities.
Although the modular implementation introduces additional coordination artifacts (flows, lifecycle management, module executables), the measurements show that executable behavior is decomposed into smaller capability-specific artifacts, while architectural evolution is localized to those capability artifacts instead of the complete task Behavior Tree.

No conclusion in this report relies on graph density, generic degree, unqualified fan-in/fan-out, or estimated modification scope. The scenario claims are limited to implemented BT XML variants and automatically computed node counts: original BT artifact size, final BT artifact size after the implemented change, added nodes, removed nodes, nodes changed in place, execution locations modified, and affected fallback/retry/recovery nodes.
