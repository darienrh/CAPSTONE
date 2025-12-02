Summary of Changes: 

- runner.py: changed a few lines so that the script skips switches and only runs diagnostic on running routers, (easier for testing can change later)

- runner.py: added final completion summary 

- added history directory: 
- stores run logs with completion summary and timestamps
- stores all running devices stable configs as a default case to revert to incase a problem is outside our decision trees.

- added function to runner.py that allows the user to save all stable running configurations in history directory ( in case we need to revert back, and also so the runner has context for specific fixes, for example fixing the RID, it needs to know what the correct RID should be)
- added terminal length 0 command to exec before any show runs in order to capture show runs properly without sending enter keystrokes

- fixed interface tree to only detect shut interfaces as problems if they have a assigned IP address. 

Created config_parser.py which extracts values from stable configs 

Optimized runner.py to be faster with parallel device scanning, reduced timeouts, implemented some caching, and other optimizations
Created problem3.py injection script with all problems for each tree
----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
TO DO ( BEFORE THURSDAY ): 
- Add prompt to runner to apply all fixes at once instead of one by one

Fix runner and decision trees to detect these remaining problems:
✓ R2: EIGRP stub configured - MISSING
✓ R2: EIGRP non-default timers on FastEthernet0/0 - MISSING
✓ R5: OSPF stub area - MISSING
✓ R6: OSPF duplicate router ID - MISSING

Whats Working: 
✓ R1: FastEthernet1/0 shutdown ✓
✓ R1: EIGRP passive interface FastEthernet2/0 ✓
✓ R3: EIGRP non-default K-values ✓
✓ R3: FastEthernet0/0 shutdown ✓
✓ R4: FastEthernet0/0 shutdown ✓
✓ R4: OSPF non-default timers on Serial0/0 ✓
✓ R5: OSPF wrong area on Serial0/1 ✓
✓ R6: OSPF passive interface FastEthernet0/0 ✓

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

Steps to run 
1. Download all the shit
2. Via GNS3 GUI connect SSH 
3. start devices 
4. Open R1 and R2 consoles to see the commands run (Xterm application should pop up on left side after clicking open console)
5. execute troubleshooter

cd inject_problem
python3 problem2.0.py

cd .. 
cd AI_troubleshoot
python3 runner.py

(select R1, R2)

