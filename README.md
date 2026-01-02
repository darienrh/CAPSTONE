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
# Download Latest VM image to make thing easier (jan 02 2026) 
https://drive.google.com/drive/folders/1iNbugmg0TK6bgDJ0iECrnOcb9gcPbOUQ?usp=drive_link

----------------------------------------------------------------------------------------------------------
WORK TO DO: 
1. knowledge_base.py
Create _initialize_basic_rules() with 10-15 rules from existing trees
Implement get_matching_rules() with basic pattern matching
Create add_problem_solution_pair() for history tracking
Test file runs independently (can create instance and call methods)

2. fix_recommender.py
Complete _load_fix_templates() with 10-15 templates
Implement customize_fix() method with placeholder replacement
Create basic validate_fix() logic with simple safety checks
Test template loading and customization independently

3. detection/init.py
Add symptoms extraction logic to Problem class
Add to_ai_format() method to Problem class
Update standardize_problem_dict() to include AI fields
Test with sample problem data

4. eigrp_tree.py (Testing/Fixing)
Test check_eigrp_interface_timers() with missing baseline data
Add severity scoring to troubleshoot_eigrp() output
Fix debug parsing for ambiguous error messages
Ensure all problems use standardized format from Step 3

5. ospf_tree.py (Testing/Fixing)
Fix check_ospf_enabled_interfaces() network matching logic
Update check_area_assignments() to use real baseline lookup
Refine router ID conflict detection
Ensure all problems use standardized format from Step 3

6. interface_tree.py (Testing/Fixing)
Ensure all outputs use Problem class format from Step 3
Add severity scoring based on interface criticality
Test all detection functions work correctly
Verify standardized output format

