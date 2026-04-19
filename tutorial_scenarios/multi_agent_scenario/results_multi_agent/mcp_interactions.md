# MCP Interaction Log

| # | Window | Sim time | Actor | Kind | Status | Detail |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | None | 0 | system | tool:create_simulation | ok | initialize multi-agent simulation |
| 2 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 0 |
| 3 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 1 |
| 4 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 2 |
| 5 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 3 |
| 6 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 4 |
| 7 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 5 |
| 8 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 6 |
| 9 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 7 |
| 10 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 8 |
| 11 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 9 |
| 12 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 10 |
| 13 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 11 |
| 14 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 12 |
| 15 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 13 |
| 16 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 14 |
| 17 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 15 |
| 18 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 16 |
| 19 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 17 |
| 20 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 18 |
| 21 | None | 0 | system | tool:deploy_application_vnfs | ok | initial random replica 19 |
| 22 | 0 | 100 | system | tool:schedule_for | ok | - |
| 23 | 0 | 200 | system | tool:wait_until_ready | ok | - |
| 24 | 0 | 200 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 25 | 0 | 200 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 26 | 0 | 200 | MonitoringAgent | assessment | - | window=0 incidents=0 overloaded_nodes=0 congested_links=0 |
| 27 | 0 | 200 | PlacementAgent | decision | - | window=0 strategy=balanced actions=0 |
| 28 | 1 | 200 | system | tool:schedule_for | ok | - |
| 29 | 1 | 400 | system | tool:wait_until_ready | ok | - |
| 30 | 1 | 400 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 31 | 1 | 400 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 32 | 1 | 400 | MonitoringAgent | assessment | - | window=1 incidents=0 overloaded_nodes=0 congested_links=0 |
| 33 | 1 | 400 | PlacementAgent | decision | - | window=1 strategy=balanced actions=0 |
| 34 | 2 | 400 | system | tool:schedule_for | ok | - |
| 35 | 2 | 600 | system | tool:wait_until_ready | ok | - |
| 36 | 2 | 600 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 37 | 2 | 600 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 38 | 2 | 600 | MonitoringAgent | assessment | - | window=2 incidents=4 overloaded_nodes=0 congested_links=2 |
| 39 | 2 | 600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 40 | 2 | 600 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 41 | 2 | 600 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 42 | 2 | 600 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_ING for Perception Pipeline |
| 43 | 2 | 600 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_FUS for Perception Pipeline |
| 44 | 2 | 600 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_PLN for Perception Pipeline |
| 45 | 2 | 600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 46 | 2 | 600 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 47 | 2 | 600 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 48 | 2 | 600 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_MON for Telemetry Monitoring |
| 49 | 2 | 600 | PlacementAgent | decision | - | window=2 strategy=congestion actions=4 |
| 50 | 3 | 600 | system | tool:schedule_for | ok | - |
| 51 | 3 | 800 | system | tool:wait_until_ready | ok | - |
| 52 | 3 | 800 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 53 | 3 | 800 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 54 | 3 | 800 | MonitoringAgent | assessment | - | window=3 incidents=8 overloaded_nodes=0 congested_links=7 |
| 55 | 3 | 800 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 56 | 3 | 800 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 57 | 3 | 800 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 58 | 3 | 800 | PlacementAgent | tool:move_application_vnf | ok | consolidate VNF due to placement-cost budget |
| 59 | 3 | 800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 60 | 3 | 800 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 61 | 3 | 800 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 62 | 3 | 800 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_MON for Telemetry Monitoring |
| 63 | 3 | 800 | PlacementAgent | decision | - | window=3 strategy=cost actions=2 |
| 64 | 4 | 800 | system | tool:schedule_for | ok | - |
| 65 | 4 | 1000 | system | tool:wait_until_ready | ok | - |
| 66 | 4 | 1000 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 67 | 4 | 1000 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 68 | 4 | 1000 | MonitoringAgent | assessment | - | window=4 incidents=23 overloaded_nodes=0 congested_links=21 |
| 69 | 4 | 1000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 70 | 4 | 1000 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 71 | 4 | 1000 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 72 | 4 | 1000 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_ING for Perception Pipeline |
| 73 | 4 | 1000 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_FUS for Perception Pipeline |
| 74 | 4 | 1000 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_PLN for Perception Pipeline |
| 75 | 4 | 1000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 76 | 4 | 1000 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 77 | 4 | 1000 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 78 | 4 | 1000 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_MON for Telemetry Monitoring |
| 79 | 4 | 1000 | PlacementAgent | decision | - | window=4 strategy=congestion actions=4 |
| 80 | 5 | 1000 | system | tool:schedule_for | ok | - |
| 81 | 5 | 1200 | system | tool:wait_until_ready | ok | - |
| 82 | 5 | 1200 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 83 | 5 | 1200 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 84 | 5 | 1200 | MonitoringAgent | assessment | - | window=5 incidents=48 overloaded_nodes=7 congested_links=38 |
| 85 | 5 | 1200 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 86 | 5 | 1200 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 87 | 5 | 1200 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 88 | 5 | 1200 | PlacementAgent | tool:move_application_vnf | ok | consolidate VNF due to placement-cost budget |
| 89 | 5 | 1200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 90 | 5 | 1200 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 91 | 5 | 1200 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 92 | 5 | 1200 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_ING for Perception Pipeline |
| 93 | 5 | 1200 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_FUS for Perception Pipeline |
| 94 | 5 | 1200 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_PLN for Perception Pipeline |
| 95 | 5 | 1200 | PlacementAgent | decision | - | window=5 strategy=cost actions=4 |
| 96 | 6 | 1200 | system | tool:schedule_for | ok | - |
| 97 | 6 | 1400 | system | tool:wait_until_ready | ok | - |
| 98 | 6 | 1400 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 99 | 6 | 1400 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 100 | 6 | 1400 | MonitoringAgent | assessment | - | window=6 incidents=54 overloaded_nodes=8 congested_links=44 |
| 101 | 6 | 1400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 102 | 6 | 1400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 103 | 6 | 1400 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 104 | 6 | 1400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 105 | 6 | 1400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 106 | 6 | 1400 | PlacementAgent | tool:move_application_vnf | ok | move 0_NEG away from overloaded node |
| 107 | 6 | 1400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 108 | 6 | 1400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 109 | 6 | 1400 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 110 | 6 | 1400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 111 | 6 | 1400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 112 | 6 | 1400 | PlacementAgent | tool:move_application_vnf | ok | move 0_DIS away from overloaded node |
| 113 | 6 | 1400 | PlacementAgent | decision | - | window=6 strategy=overload actions=4 |
| 114 | 7 | 1400 | system | tool:schedule_for | ok | - |
| 115 | 7 | 1600 | system | tool:wait_until_ready | ok | - |
| 116 | 7 | 1600 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 117 | 7 | 1600 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 118 | 7 | 1600 | MonitoringAgent | assessment | - | window=7 incidents=56 overloaded_nodes=7 congested_links=47 |
| 119 | 7 | 1600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 120 | 7 | 1600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 121 | 7 | 1600 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 122 | 7 | 1600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 123 | 7 | 1600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 124 | 7 | 1600 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 125 | 7 | 1600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 126 | 7 | 1600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 127 | 7 | 1600 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 128 | 7 | 1600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 129 | 7 | 1600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 130 | 7 | 1600 | PlacementAgent | tool:move_application_vnf | error | move 0_ING away from overloaded node |
| 131 | 7 | 1600 | PlacementAgent | decision | - | window=7 strategy=overload actions=4 |
| 132 | 8 | 1600 | system | tool:schedule_for | ok | - |
| 133 | 8 | 1800 | system | tool:wait_until_ready | ok | - |
| 134 | 8 | 1800 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 135 | 8 | 1800 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 136 | 8 | 1800 | MonitoringAgent | assessment | - | window=8 incidents=65 overloaded_nodes=6 congested_links=57 |
| 137 | 8 | 1800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 138 | 8 | 1800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 139 | 8 | 1800 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 140 | 8 | 1800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 141 | 8 | 1800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 142 | 8 | 1800 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 143 | 8 | 1800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 144 | 8 | 1800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 145 | 8 | 1800 | PlacementAgent | tool:move_application_vnf | error | move 0_ING away from overloaded node |
| 146 | 8 | 1800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 147 | 8 | 1800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 148 | 8 | 1800 | PlacementAgent | tool:move_application_vnf | error | move 0_ING away from overloaded node |
| 149 | 8 | 1800 | PlacementAgent | decision | - | window=8 strategy=overload actions=4 |
| 150 | 9 | 1800 | system | tool:schedule_for | ok | - |
| 151 | 9 | 2000 | system | tool:wait_until_ready | ok | - |
| 152 | 9 | 2000 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 153 | 9 | 2000 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 154 | 9 | 2000 | MonitoringAgent | assessment | - | window=9 incidents=78 overloaded_nodes=5 congested_links=71 |
| 155 | 9 | 2000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 156 | 9 | 2000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 157 | 9 | 2000 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 158 | 9 | 2000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 159 | 9 | 2000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 160 | 9 | 2000 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 161 | 9 | 2000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 162 | 9 | 2000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 163 | 9 | 2000 | PlacementAgent | tool:move_application_vnf | ok | move 0_DIS away from overloaded node |
| 164 | 9 | 2000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 165 | 9 | 2000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 166 | 9 | 2000 | PlacementAgent | tool:move_application_vnf | ok | move 0_DIS away from overloaded node |
| 167 | 9 | 2000 | PlacementAgent | decision | - | window=9 strategy=overload actions=4 |
| 168 | 10 | 2000 | system | tool:schedule_for | ok | - |
| 169 | 10 | 2200 | system | tool:wait_until_ready | ok | - |
| 170 | 10 | 2200 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 171 | 10 | 2200 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 172 | 10 | 2200 | MonitoringAgent | assessment | - | window=10 incidents=83 overloaded_nodes=4 congested_links=76 |
| 173 | 10 | 2200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 174 | 10 | 2200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 175 | 10 | 2200 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 176 | 10 | 2200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 177 | 10 | 2200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 178 | 10 | 2200 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 179 | 10 | 2200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 180 | 10 | 2200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 181 | 10 | 2200 | PlacementAgent | tool:move_application_vnf | error | move 0_ING away from overloaded node |
| 182 | 10 | 2200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 183 | 10 | 2200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 184 | 10 | 2200 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 185 | 10 | 2200 | PlacementAgent | decision | - | window=10 strategy=overload actions=4 |
| 186 | 11 | 2200 | system | tool:schedule_for | ok | - |
| 187 | 11 | 2400 | system | tool:wait_until_ready | ok | - |
| 188 | 11 | 2400 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 189 | 11 | 2400 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 190 | 11 | 2400 | MonitoringAgent | assessment | - | window=11 incidents=89 overloaded_nodes=4 congested_links=82 |
| 191 | 11 | 2400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 192 | 11 | 2400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 193 | 11 | 2400 | PlacementAgent | tool:move_application_vnf | ok | move 0_PLN away from overloaded node |
| 194 | 11 | 2400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 195 | 11 | 2400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 196 | 11 | 2400 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 197 | 11 | 2400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 198 | 11 | 2400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 199 | 11 | 2400 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 200 | 11 | 2400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 201 | 11 | 2400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 202 | 11 | 2400 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 203 | 11 | 2400 | PlacementAgent | decision | - | window=11 strategy=overload actions=4 |
| 204 | 12 | 2400 | system | tool:schedule_for | ok | - |
| 205 | 12 | 2600 | system | tool:wait_until_ready | ok | - |
| 206 | 12 | 2600 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 207 | 12 | 2600 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 208 | 12 | 2600 | MonitoringAgent | assessment | - | window=12 incidents=96 overloaded_nodes=4 congested_links=88 |
| 209 | 12 | 2600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 210 | 12 | 2600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 211 | 12 | 2600 | PlacementAgent | tool:move_application_vnf | ok | move 0_DIS away from overloaded node |
| 212 | 12 | 2600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 213 | 12 | 2600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 214 | 12 | 2600 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 215 | 12 | 2600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 216 | 12 | 2600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 217 | 12 | 2600 | PlacementAgent | tool:move_application_vnf | ok | move 0_ING away from overloaded node |
| 218 | 12 | 2600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 219 | 12 | 2600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 220 | 12 | 2600 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 221 | 12 | 2600 | PlacementAgent | decision | - | window=12 strategy=overload actions=4 |
| 222 | 13 | 2600 | system | tool:schedule_for | ok | - |
| 223 | 13 | 2800 | system | tool:wait_until_ready | ok | - |
| 224 | 13 | 2800 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 225 | 13 | 2800 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 226 | 13 | 2800 | MonitoringAgent | assessment | - | window=13 incidents=101 overloaded_nodes=3 congested_links=94 |
| 227 | 13 | 2800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 228 | 13 | 2800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 229 | 13 | 2800 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 230 | 13 | 2800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 231 | 13 | 2800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 232 | 13 | 2800 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 233 | 13 | 2800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 234 | 13 | 2800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 235 | 13 | 2800 | PlacementAgent | tool:move_application_vnf | ok | move 0_PLN away from overloaded node |
| 236 | 13 | 2800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 237 | 13 | 2800 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 238 | 13 | 2800 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 239 | 13 | 2800 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_ING for Perception Pipeline |
| 240 | 13 | 2800 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_FUS for Perception Pipeline |
| 241 | 13 | 2800 | PlacementAgent | tool:replicate_application_vnf | ok | replicate 0_PLN for Perception Pipeline |
| 242 | 13 | 2800 | PlacementAgent | decision | - | window=13 strategy=overload actions=4 |
| 243 | 14 | 2800 | system | tool:schedule_for | ok | - |
| 244 | 14 | 3000 | system | tool:wait_until_ready | ok | - |
| 245 | 14 | 3000 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 246 | 14 | 3000 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 247 | 14 | 3000 | MonitoringAgent | assessment | - | window=14 incidents=109 overloaded_nodes=4 congested_links=101 |
| 248 | 14 | 3000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 249 | 14 | 3000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 250 | 14 | 3000 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 251 | 14 | 3000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 252 | 14 | 3000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 253 | 14 | 3000 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 254 | 14 | 3000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 255 | 14 | 3000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 256 | 14 | 3000 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 257 | 14 | 3000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 258 | 14 | 3000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 259 | 14 | 3000 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 260 | 14 | 3000 | PlacementAgent | decision | - | window=14 strategy=overload actions=4 |
| 261 | 15 | 3000 | system | tool:schedule_for | ok | - |
| 262 | 15 | 3200 | system | tool:wait_until_ready | ok | - |
| 263 | 15 | 3200 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 264 | 15 | 3200 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 265 | 15 | 3200 | MonitoringAgent | assessment | - | window=15 incidents=113 overloaded_nodes=4 congested_links=105 |
| 266 | 15 | 3200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 267 | 15 | 3200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 268 | 15 | 3200 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 269 | 15 | 3200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 270 | 15 | 3200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 271 | 15 | 3200 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 272 | 15 | 3200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 273 | 15 | 3200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 274 | 15 | 3200 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 275 | 15 | 3200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 276 | 15 | 3200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 277 | 15 | 3200 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 278 | 15 | 3200 | PlacementAgent | decision | - | window=15 strategy=overload actions=4 |
| 279 | 16 | 3200 | system | tool:schedule_for | ok | - |
| 280 | 16 | 3400 | system | tool:wait_until_ready | ok | - |
| 281 | 16 | 3400 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 282 | 16 | 3400 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 283 | 16 | 3400 | MonitoringAgent | assessment | - | window=16 incidents=119 overloaded_nodes=5 congested_links=110 |
| 284 | 16 | 3400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 285 | 16 | 3400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 286 | 16 | 3400 | PlacementAgent | tool:move_application_vnf | ok | move 0_NEG away from overloaded node |
| 287 | 16 | 3400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 288 | 16 | 3400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 289 | 16 | 3400 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 290 | 16 | 3400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 291 | 16 | 3400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 292 | 16 | 3400 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 293 | 16 | 3400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 294 | 16 | 3400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 295 | 16 | 3400 | PlacementAgent | tool:move_application_vnf | ok | move 0_PLN away from overloaded node |
| 296 | 16 | 3400 | PlacementAgent | decision | - | window=16 strategy=overload actions=4 |
| 297 | 17 | 3400 | system | tool:schedule_for | ok | - |
| 298 | 17 | 3600 | system | tool:wait_until_ready | ok | - |
| 299 | 17 | 3600 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 300 | 17 | 3600 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 301 | 17 | 3600 | MonitoringAgent | assessment | - | window=17 incidents=120 overloaded_nodes=4 congested_links=111 |
| 302 | 17 | 3600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 303 | 17 | 3600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 304 | 17 | 3600 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 305 | 17 | 3600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 306 | 17 | 3600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 307 | 17 | 3600 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 308 | 17 | 3600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 309 | 17 | 3600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 310 | 17 | 3600 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 311 | 17 | 3600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 312 | 17 | 3600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 313 | 17 | 3600 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 314 | 17 | 3600 | PlacementAgent | decision | - | window=17 strategy=overload actions=4 |
| 315 | 18 | 3600 | system | tool:schedule_for | ok | - |
| 316 | 18 | 3800 | system | tool:wait_until_ready | ok | - |
| 317 | 18 | 3800 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 318 | 18 | 3800 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 319 | 18 | 3800 | MonitoringAgent | assessment | - | window=18 incidents=124 overloaded_nodes=6 congested_links=113 |
| 320 | 18 | 3800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 321 | 18 | 3800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 322 | 18 | 3800 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 323 | 18 | 3800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 324 | 18 | 3800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 325 | 18 | 3800 | PlacementAgent | tool:move_application_vnf | ok | move 0_PLN away from overloaded node |
| 326 | 18 | 3800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 327 | 18 | 3800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 328 | 18 | 3800 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 329 | 18 | 3800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 330 | 18 | 3800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 331 | 18 | 3800 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 332 | 18 | 3800 | PlacementAgent | decision | - | window=18 strategy=overload actions=4 |
| 333 | 19 | 3800 | system | tool:schedule_for | ok | - |
| 334 | 19 | 4000 | system | tool:wait_until_ready | ok | - |
| 335 | 19 | 4000 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 336 | 19 | 4000 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 337 | 19 | 4000 | MonitoringAgent | assessment | - | window=19 incidents=125 overloaded_nodes=7 congested_links=114 |
| 338 | 19 | 4000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 339 | 19 | 4000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 340 | 19 | 4000 | PlacementAgent | tool:move_application_vnf | ok | move 0_NEG away from overloaded node |
| 341 | 19 | 4000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 342 | 19 | 4000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 343 | 19 | 4000 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 344 | 19 | 4000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 345 | 19 | 4000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 346 | 19 | 4000 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 347 | 19 | 4000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 348 | 19 | 4000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 349 | 19 | 4000 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 350 | 19 | 4000 | PlacementAgent | decision | - | window=19 strategy=overload actions=4 |
| 351 | 20 | 4000 | system | tool:schedule_for | ok | - |
| 352 | 20 | 4200 | system | tool:wait_until_ready | ok | - |
| 353 | 20 | 4200 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 354 | 20 | 4200 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 355 | 20 | 4200 | MonitoringAgent | assessment | - | window=20 incidents=130 overloaded_nodes=7 congested_links=118 |
| 356 | 20 | 4200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 357 | 20 | 4200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 358 | 20 | 4200 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 359 | 20 | 4200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 360 | 20 | 4200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 361 | 20 | 4200 | PlacementAgent | tool:move_application_vnf | ok | move 0_PLN away from overloaded node |
| 362 | 20 | 4200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 363 | 20 | 4200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 364 | 20 | 4200 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 365 | 20 | 4200 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 366 | 20 | 4200 | PlacementAgent | tool:list_simulation_users | ok | - |
| 367 | 20 | 4200 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 368 | 20 | 4200 | PlacementAgent | decision | - | window=20 strategy=overload actions=4 |
| 369 | 21 | 4200 | system | tool:schedule_for | ok | - |
| 370 | 21 | 4400 | system | tool:wait_until_ready | ok | - |
| 371 | 21 | 4400 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 372 | 21 | 4400 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 373 | 21 | 4400 | MonitoringAgent | assessment | - | window=21 incidents=135 overloaded_nodes=7 congested_links=123 |
| 374 | 21 | 4400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 375 | 21 | 4400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 376 | 21 | 4400 | PlacementAgent | tool:move_application_vnf | ok | move 0_NEG away from overloaded node |
| 377 | 21 | 4400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 378 | 21 | 4400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 379 | 21 | 4400 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 380 | 21 | 4400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 381 | 21 | 4400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 382 | 21 | 4400 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 383 | 21 | 4400 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 384 | 21 | 4400 | PlacementAgent | tool:list_simulation_users | ok | - |
| 385 | 21 | 4400 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 386 | 21 | 4400 | PlacementAgent | decision | - | window=21 strategy=overload actions=4 |
| 387 | 22 | 4400 | system | tool:schedule_for | ok | - |
| 388 | 22 | 4600 | system | tool:wait_until_ready | ok | - |
| 389 | 22 | 4600 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 390 | 22 | 4600 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 391 | 22 | 4600 | MonitoringAgent | assessment | - | window=22 incidents=133 overloaded_nodes=7 congested_links=120 |
| 392 | 22 | 4600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 393 | 22 | 4600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 394 | 22 | 4600 | PlacementAgent | tool:move_application_vnf | ok | move 0_PLN away from overloaded node |
| 395 | 22 | 4600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 396 | 22 | 4600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 397 | 22 | 4600 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 398 | 22 | 4600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 399 | 22 | 4600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 400 | 22 | 4600 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 401 | 22 | 4600 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 402 | 22 | 4600 | PlacementAgent | tool:list_simulation_users | ok | - |
| 403 | 22 | 4600 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 404 | 22 | 4600 | PlacementAgent | decision | - | window=22 strategy=overload actions=4 |
| 405 | 23 | 4600 | system | tool:schedule_for | ok | - |
| 406 | 23 | 4800 | system | tool:wait_until_ready | ok | - |
| 407 | 23 | 4800 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 408 | 23 | 4800 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 409 | 23 | 4800 | MonitoringAgent | assessment | - | window=23 incidents=131 overloaded_nodes=7 congested_links=119 |
| 410 | 23 | 4800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 411 | 23 | 4800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 412 | 23 | 4800 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 413 | 23 | 4800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 414 | 23 | 4800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 415 | 23 | 4800 | PlacementAgent | tool:move_application_vnf | ok | move 0_NEG away from overloaded node |
| 416 | 23 | 4800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 417 | 23 | 4800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 418 | 23 | 4800 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 419 | 23 | 4800 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 420 | 23 | 4800 | PlacementAgent | tool:list_simulation_users | ok | - |
| 421 | 23 | 4800 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 422 | 23 | 4800 | PlacementAgent | decision | - | window=23 strategy=overload actions=4 |
| 423 | 24 | 4800 | system | tool:schedule_for | ok | - |
| 424 | 24 | 5000 | system | tool:wait_until_ready | ok | - |
| 425 | 24 | 5000 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 426 | 24 | 5000 | MonitoringAgent | tool:get_simulation_network_metrics | ok | - |
| 427 | 24 | 5000 | MonitoringAgent | assessment | - | window=24 incidents=135 overloaded_nodes=7 congested_links=123 |
| 428 | 24 | 5000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 429 | 24 | 5000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 430 | 24 | 5000 | PlacementAgent | tool:move_application_vnf | ok | move 0_PLN away from overloaded node |
| 431 | 24 | 5000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 432 | 24 | 5000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 433 | 24 | 5000 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 434 | 24 | 5000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 435 | 24 | 5000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 436 | 24 | 5000 | PlacementAgent | tool:move_application_vnf | ok | move 0_FUS away from overloaded node |
| 437 | 24 | 5000 | PlacementAgent | tool:list_simulation_node_placements | ok | - |
| 438 | 24 | 5000 | PlacementAgent | tool:list_simulation_users | ok | - |
| 439 | 24 | 5000 | PlacementAgent | tool:move_application_vnf | error | move 0_FUS away from overloaded node |
| 440 | 24 | 5000 | PlacementAgent | decision | - | window=24 strategy=overload actions=4 |
| 441 | None | 5000 | system | tool:stop_simulation | ok | - |
| 442 | None | 5000 | MonitoringAgent | tool:get_simulation_application_metrics | ok | - |
| 443 | None | 5000 | system | tool:list_simulation_deployed_applications | ok | - |
| 444 | None | 5000 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 445 | None | 5000 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
| 446 | None | 5000 | PlacementAgent | tool:list_simulation_application_vnfs | ok | - |
