repeats = 100000

with open("./HOMEM.GCO", "w") as myfile:

    cmds = ["G28 A", "G28 Z", "G28 X", "G28 Y", f"G1 X60 Y110"]
    loops_cmds = ["G28 A", "G28 Z", "G28 X",
                  "G28 Y", "G1 X110 Y20 Z10 A3 F2000"]
    for _i in range(repeats):
        cmds += loops_cmds
    for cmd in cmds:
        myfile.write(f"{cmd}\n")
