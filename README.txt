Summary of Changes: (2 basic decision Trees Now working )

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Current Directory Structure In Ubuntu VM:

/home/user1/
│
├── AI_troubleshoot/
│   ├── runner.py
│   ├── interface_tree.py
│   └── eigrp_tree.py
│
└── inject_problem/
    ├── eigrp_stub.py
    ├── interface_shut.py
    ├── pingdemo.py
    └── problem2.0.py (R1 interface shut + R2 eigrp stub command)

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
1. Created and setup Ubuntu image complete with GNS3 installed, and shared with the team

2. Refactored prototype to use teammates decision trees

3. Modified Ubuntu image with python and GNS3 dependencies all setup, GNS3 project file added to image, ping_demo.py file created showcasing a python script making basic changes to the topology and fixing them. 

4. Created new problem injection scripts

5. Created new project directory structure and files for AI troubleshooter

6. Fixed and expanded initial decision trees to work, created runner,py as a main orchestrator to run the troubleshooter

7. Fixed GNS3 console windows to be able to open multiple windows (changed from gnome to xterm, modified gns3 compose file)

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
