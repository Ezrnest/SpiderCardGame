from base.Core import Core
from base.Interface import Interface


class CommandLineInterface(Interface):

    def printAll(self):
        core = self.core
        print(f"Finished: {core.finishedCount}        Base: {len(core.base)}")
        print("----0----1----2----3----4----5----6----7----8----9---")
        i = 0
        while True:
            has = False
            line = str(i) + ": "
            for stack in core.stacks:
                if len(stack) <= i:
                    line += "     "
                    continue
                has = True
                line += str(stack[i].gameStr())
                line += "  "
            if not has:
                break
            print(line)
            i += 1
        print()
        print()

    def onStart(self):
        print("Game started!")

    def notifyRedraw(self):
        self.printAll()

    def onWin(self):
        print("You win!")


def main():
    interface = CommandLineInterface()
    core = Core()
    core.registerInterface(interface)
    core.registerPlayer("Null")
    core.startGame()
    while not core.gameEnded:
        command = input()
        if command.startswith("mv"):
            command = command.split(" ")
            srcStr = command[1]
            destStr = command[2]
            try:
                s = int(srcStr[0])
                if len(srcStr) < 2:
                    src = (s, len(core.stacks[s])-1)
                else:
                    src = (int(srcStr[0]), int(srcStr[1]))
                dest = int(destStr)
            except:
                print("Invalid index!")
                continue
            if not core.askMove(src, dest):
                print("Cannot move!")
        elif command.startswith("deal"):
            if not core.askDeal():
                print("No card left!")
        elif command.startswith("undo"):
            if not core.askUndo():
                print("Cannot undo!")
        elif command.startswith("redo"):
            if not core.askRedo():
                print("Cannot redo!")
        else:
            print("Invalid command!")
    pass


if __name__ == '__main__':
    main()
