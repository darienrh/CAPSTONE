# CAPSTONE
REPO FOR THE 2025 CAPSTONE PROJECT
Sam, Rayyan, Mersha, Xin, Darien, Rafay
----------------------------------------------------------------------------------------------------------
# Download Latest VM image to make thing easier (jan 03 2026) 
https://drive.google.com/drive/folders/1iNbugmg0TK6bgDJ0iECrnOcb9gcPbOUQ?usp=drive_link
----------------------------------------------------------------------------------------------------------
# WORK TO DO: 

Core Modules
core/config_manager.py
- Add docstrings to all methods
- Write unit tests for parsing functions

core/knowledge_base.py
- Add learn_from_outcome() method for ML feedback loop
- Implement find_similar_problems_ml() with feature extraction
- Add _calculate_similarity() for problem comparison
- Create _analyze_failure() to learn from fix failures
- Add Bayesian probability update methods
- Add method to export training data for ML
- Ensure all rule IDs are unique
- Document rule format and structure

core/inference_engine.py
- Implement diagnose_bayesian() with Bayes theorem
- Add prior probability tables for all problem types
- Add likelihood tables mapping symptoms to problems
- Implement update_priors() to learn from outcomes
- Complete execute_reasoning_chain() implementation
- Add _explain_chain() for human-readable explanations
- Implement _ensemble_predictions() to combine rule-based + ML results
- Make chain_reasoning() actually execute in workflow
- Connect handle_uncertainty() to main workflow
- Add tests for confidence calculations

core/ml_classifier.py (NEW FILE)
- Create ProblemClassifier class
- Implement train_from_history() method
- Implement predict_problem_type() method
- Add _extract_ml_features() for feature engineering
- Add save_model() and load_model() methods
- Integrate scikit-learn RandomForestClassifier
- Add performance metrics (accuracy, precision, recall)
- Add minimum training data validation


Detection Modules
detection/problem_detector.py
- Accept knowledge_base and inference_engine parameters in __init__
- Add _convert_to_symptoms() method to transform problems
- Call inference_engine.diagnose() after detection
- Add detect_anomalies() for predictive maintenance
- Store and maintain baseline metrics per device
- Add error handling for failed telnet connections
- Improve parallel scanning reliability and error recovery
- Add logging for all detection operations

detection/interface_tree.py
- Validate IP configs before comparing to baseline
- - Handle interfaces without baseline data gracefully
Add test cases for edge conditions
Add more descriptive error messages

detection/eigrp_tree.py

Test and fix timer fix commands on real routers
Verify get_eigrp_fix_commands() generates correct command syntax
Ensure AS number is used correctly in all timer commands
Handle missing baseline data without crashing
Add validation before applying network statement changes
Test all fix commands on live routers
Document expected vs actual timer formats

detection/ospf_tree.py

Test and fix timer fix commands on real routers
Verify hello/dead interval commands work correctly
Implement automatic router ID conflict resolution
Improve area mismatch detection accuracy
Add better duplicate RID resolution logic
Test all fix commands on live routers
Document OSPF area design expectations


Resolution Modules
resolution/fix_applier.py

Accept fix_recommender parameter in __init__
Add _apply_fix_plan() method for AI-generated plans
Add _apply_single_fix() helper method
Call fix_recommender.validate_fix() before applying changes
Call fix_recommender.learn_from_fix_result() after applying
Add rollback capability on partial failure
Improve verification logic after fix application
Add transaction support (all-or-nothing for multi-step fixes)
Add tests for fix application

resolution/fix_recommender.py

Implement learn_from_fix_result() method
Improve _calculate_similarity() accuracy
Add more fix templates for common issues
Better prerequisite checking logic
More accurate risk assessment algorithms
Integrate with main workflow in runner
Document fix plan format


Utility Modules
utils/telnet_utils.py

Add retry logic for failed commands
Better timeout handling
Add connection pooling for efficiency
Add mock telnet implementation for testing
Document all functions with examples

utils/reporter.py

Add AI confidence visualization in tables
Add reasoning chain display in output
Show ML predictions vs rule-based predictions
Add charts for problem trends over time
Improve report formatting

utils/network_utils.py

Add IPv6 support
Add unit tests for all functions
Add usage examples in docstrings


Main Runner
runner.py

Initialize InferenceEngine in __init__
Initialize FixRecommender in __init__
Pass AI components to ProblemDetector
Pass AI components to FixApplier
Add train_ml_model() method
Add uncertainty handling in run_diagnostics()
Display AI reasoning in results output
Fix restore timeout issues in parallel mode
Better error handling in GNS3 connection
Add validation before destructive changes
Improve connection cleanup on errors
Add menu option for training mode
Show confidence scores in diagnostic output
Add help text for all menu options
