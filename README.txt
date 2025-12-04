Summary of Changes: 

- problem1.py works to do a basic action on each tree
- configuration versioning is fully implemented (minus some possible bugs with reverting all devices to past configs)
- more clean output when running scripts
- overall program is closer to being able to fix all problems in problem2.py
- program is not detecting any false positives anymore

Info: in the GNS3 topology R5 had wrong ospf area, make sure to fix that and add RIDs to OSPF routers 4.4.4.4, 5.5.5.5, etc before you run.

Next Steps:
fully implement problem2.py

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

Steps to run 
1. Download all the shit
2. Via GNS3 GUI connect SSH 
3. start devices 
4. Open R1 and R2 consoles to see the commands run (Xterm application should pop up on left side after clicking open console)
5. execute troubleshooter

cd inject_problem
python3 problem1.py

cd .. 
cd AI_troubleshoot
python3 runner.py



