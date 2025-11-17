AI Tshooter

Directory Structure:
AI_tshooter/
├── __init__.py
├── models/
│   ├── __init__.py
│   └── diagnostic.py          # Data models
├── analyzers/
│   ├── __init__.py
│   ├── base.py                # Base analyzer class
│   ├── interface_analyzer.py
│   ├── vlan_analyzer.py
│   ├── ospf_analyzer.py
│   ├── bgp_analyzer.py
│   ├── eigrp_analyzer.py
│   ├── performance_analyzer.py
│   └── other_analyzers.py     # Gateway, NTP, IPv6, GRE
├── engine.py                  # Main decision tree engine
├── formatters.py              # Output formatting
└── utils.py                   # Helper functions

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
Data Flow:

0. User injects problems to GNS3 via python script
1. User opens terminal and runs decision tree analysis (python engine.py)
2. engine.py fetches Telemetry from prometheus, afterwards fetches every N seconds.
3. Prometheus scrapes SNMP data from GNS3
4. Telemetry data arrives, and decision tree engine starts its checks
5. decision tree calls all analyzer py files and returns results to formatters.py (results should make the problem very clear ex. "wrong AS number on R1")
6. formatters.py converts the results into natural language asking for the exact syntax configuration fix, and sends as context to LLM, Instructions will give LLM exact formatting parameters.
7. LLM returns structured configuration syntax response in file located in /responses Directory
8. engine.py then prompts user if it want to deploy the configuration change commands that are stored in the /responses Directory
9. If no--> return to main menu, If yes --> shipit.py will send python script fixing problems

----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------