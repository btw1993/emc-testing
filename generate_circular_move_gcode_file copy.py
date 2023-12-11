repeats = 100000

with open("./CIRCLE.GCO", "w") as myfile:

    cmds = ["G28 A", "G28 Z", "G28 X", "G28 Y", f"G1 X60 Y110"]
    loops_cmds = ["G2 I50 F900", "G1 Z15 F500", "G1 A5", "G1 A0", "G1 Z0 F500"]
    for _i in range(repeats):
        cmds += loops_cmds
    for cmd in cmds:
        myfile.write(f"{cmd}\n")
