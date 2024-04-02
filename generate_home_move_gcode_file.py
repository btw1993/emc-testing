repeats = 100000

with open("./HOMEM.GCO", "w") as myfile:

    cmds = []
    loops_cmds = ["G28 A", "G28 Z", "G28 X",
                  "G28 Y", "G1 Y50 A3 F2000", "G1 X110 Z10 F2000"]
    for _i in range(repeats):
        cmds += loops_cmds
    for cmd in cmds:
        myfile.write(f"{cmd}\n")
