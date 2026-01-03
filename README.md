# CAPSTONE
REPO FOR THE 2025 CAPSTONE PROJECT
Sam, Rayyan, Mersha, Xin, Darien, Rafay
----------------------------------------------------------------------------------------------------------
Current Active Shared Documents
Research:
Capstone Plan / Major Steps
https://docs.google.com/document/d/1TyNDhhldyZrOfPqjnGow5GCAIkeK4jLHP_3Sfbgk-kA/edit?usp=sharing
Decision Tree psuedo code
https://docs.google.com/document/d/1f7H4HA1FChojEzTnEbQQ3oYjpCEG2L5mY3jQq9a5j-I/edit?usp=sharing
Project Proposal 
https://docs.google.com/document/d/1klzsvzyUgRslUVBO2lblb3iecVZh41ny0jOE0XMu3iU/edit?pli=1&tab=t.0
Slides:
[https://docs.google.com/presentation/d/13dbNv432SCjMt1cS9xIPTxJNGedKuvg60prSWrYMbsk/edit?slide=id.p1#slide=id.p1](https://cmailcarletonca-my.sharepoint.com/:p:/r/personal/darienramirezhenness_cmail_carleton_ca/_layouts/15/Doc.aspx?sourcedoc=%7B7C15372C-24E8-4236-BC00-AC3A90A87E15%7D&file=CAPSTONE%20AI%20ASSISTED%20TROUBLESHOOTER.pptx&action=edit&mobileredirect=true)
----------------------------------------------------------------------------------------------------------
# Download Latest VM image to make thing easier (jan 03 2026) 
https://drive.google.com/drive/folders/1iNbugmg0TK6bgDJ0iECrnOcb9gcPbOUQ?usp=drive_link

----------------------------------------------------------------------------------------------------------
# WORK TO DO: 
# PHASE 1: Core AI Infrastructure

1. inference_engine.py 
- Basic implementation (DONE)

REMAINING:
- Add Bayesian confidence propagation for better probability updates
- Implement forward chaining for symptom → root cause
- Add backward chaining for "why" explanations
- Create conflict resolution for competing rules
- Test with real problem scenarios from your trees

2. knowledge_base.py
- 17 basic rules already initialized (DONE)
- Pattern matching implemented (DONE)
- History tracking works (DONE)

REMAINING:
- Add rule chaining (e.g., "interface down" → "no EIGRP neighbor")
- Implement rule priority/conflict resolution
- Add temporal reasoning (time-based patterns)
- Create rule validation/consistency checking
- TEST: Load KB, query rules for each problem type, verify correct matches

3. fix_recommender.py
- Template system implemented (DONE)
- KB integration working (DONE)

REMAINING:
- Add 10+ more fix templates (currently only 2)
- Implement dependency tracking between fixes
- Add rollback command generation
- Create fix validation with pre-condition checking
- TEST: Generate fixes for each problem type, verify commands are correct

-----------------------------------------------------------------------------------------
# PHASE 2: Integration Layer
1. problem_detector.py
- base implementation with problem and problemDector classes (DONE)

REMAINING:
- Update scan_device() to wrap problems in Problem class
- Add to_ai_format() conversion before sending to inference engine
- Create standardize_problem_dict() utility function
- TEST: Scan device, verify Problem objects created correctly

2. fix_applier.py
- Basic application logic works

REMAINING:
- Add pre-flight validation (call fix_recommender.validate_fix())
- Implement rollback on failure
- Add verification after each fix
- Log all fixes to knowledge base for learning
- TEST: Apply each fix type, verify success and rollback works

-----------------------------------------------------------------------------------------
# PHASE 3: Detection Tree Migration

1. interface_tree.py

REMAINING:
- add severity field to all problems
- Wrap outputs in Problem class
- Add confidence scoring
- TEST SCRIPT: Inject all interface errors, verify detection + fixes work

2. eigrp_tree.py

REMAINING:
- Add severity levels:
	- as mismatch: critical
	- k-value mismatch: high
	- hello timer mismatch: medium
	- passive interface: low
- Add confidence scoring based on evidence strength
- Handle ambiguous debug output better
- Return Problem objects instead of raw dicts

3. ospf_tree.py
- use ConfigManager's baseline directly
- Fix check_ospf_enabled_interfaces() network matching
- Improve router ID conflict detection (check for INIT state neighbors)
- Add severity/confidence to all problems
- Return Problem objects
- TEST SCRIPT: Inject all OSPF errors, verify detection + fixes

-----------------------------------------------------------------------------------------
# PHASE 4: AI Integration & Testing

1. runner.py
- Integrate inference engine into diagnostic flow
- Add diagnosis explanation to reporter
- Show AI confidence levels
- Allow user to accept/reject AI recommendations
- TEST: Run full diagnostic cycle, verify AI provides useful insights

reporter.py
- create print_diagnosis method
- create print_fix_recommendations method
- Display reasoning explanation, Add "Why?" option to show inference chain

-----------------------------------------------------------------------------------------
# PHASE 5: Machine Learning + IDS
