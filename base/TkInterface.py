from tkinter import *
from tkinter import messagebox

from base.Core import Core, DUMMY_PLAYER, Card, lastOf, GameConfig, loadGameFromFile, saveGameToFile
from base.Interface import Interface

MENU = 1
GAME = 2
STATISTICS = 3

# CARD_WIDTH = 50
# CARD_HEIGHT = 80
# SELECTED_SHOWING_HEIGHT = CARD_HEIGHT // 3
# NOT_SELECTED_SHOWING_HEIGHT = CARD_HEIGHT // 5

CARD_COLOR = "#F3F781"
DEFAULT_FONT = "Arial 16"

CARD_WIDTH_PERCENT = 0.075
CARD_HEIGHT_PERCENT = 0.2
CARD_HEIGHT_MULTIPLIER = 1.5
SELECTED_SHOWING_HEIGHT_PERCENT = 0.33
NOT_SELECTED_SHOWING_HEIGHT_PERCENT = 0.2
CARD_FONT_PERCENT = 0.32


class Rect:

    def __init__(self, upperLeft, width=50, height=80):
        self.upperLeft = upperLeft
        self.width = width
        self.height = height

    def drawCard(self, canvas: Canvas, card: Card):
        (x, y) = self.upperLeft
        fontSize = int(CARD_FONT_PERCENT * self.width)
        canvas.create_rectangle(x, y, x + self.width, y + self.height, fill=CARD_COLOR, outline="black")
        if not card.hidden:
            canvas.create_text(x + 1, y + 1, anchor=NW, text=card.gameStr(), font="Arial " + str(fontSize),
                               fill=card.color())
        pass

    def draw(self, canvas: Canvas, fill="white", outline="black"):
        (x, y) = self.upperLeft
        canvas.create_rectangle(x, y, x + self.width, y + self.height, fill=fill, outline=outline)

    def contains(self, x, y):
        (tx, ty) = self.upperLeft
        return tx <= x <= tx + self.width and ty <= y <= ty + self.height

    def intersects(self, rect):
        (tx1, ty1) = self.upperLeft
        tx2 = tx1 + self.width
        ty2 = ty1 + self.height

        (rx1, ry1) = rect.upperLeft
        rx2 = rx1 + rect.width
        ry2 = ry1 + rect.height

        return rx2 >= tx1 and ry2 >= ty1 \
               and tx2 >= rx1 and ty2 >= ry1

    pass


class TkInterface(Interface):

    def __init__(self, width=900, height=600):
        super().__init__()
        self.width = width
        self.height = height
        self.cardWidth = 50
        self.cardHeight = 80
        self.timerDelay = 100
        self.canvas: Canvas = None
        self.root = None
        self.stage = MENU
        self.config = GameConfig.loadFromFile("config.ini")
        self.core: Core = None

        self.cardRects = []
        self.stackRects = []
        self.baseRect = None
        self.selected = (-1, -1)
        self.dragging = False
        self.mousePos = (0, 0)
        self.mousePosOld = (0, 0)
        self.hasWon = False

        self.tips = None

    def run(self):
        root = Tk()
        root.title("Spider Card")
        self.root = root
        root.resizable(width=True, height=True)
        # create the root and the canvas
        canvas = Canvas(root, width=self.width, height=self.height)
        canvas.configure(bd=0, highlightthickness=0)
        canvas.pack(expand=1, fill="both")
        self.canvas = canvas
        # set up events
        # root.bind("")
        root.bind("<Button-1>", self.mousePressed)
        root.bind("<B1-Motion>", self.mouseMoved)
        root.bind("<ButtonRelease-1>", self.mouseReleased)
        root.bind("<Key>", self.keyPressed)
        root.bind("<Configure>", self.resize)
        root.protocol("WM_DELETE_WINDOW", self.onClosing)
        self.computeCardWidth()
        self.timerFired()
        self.redrawAll()
        root.mainloop()
        # and launch the app

    def onClosing(self):
        if self.stage == GAME:
            if self.config.isProfessionalMode() and not messagebox.askokcancel("Quit", "Do you want to quit?"):
                return
            self.autoSave()
        self.config.saveToFile("config.ini")
        self.root.destroy()

    def resize(self, event):
        if event.widget != self.root:
            return
        self.width = event.width
        self.height = event.height
        self.computeCardWidth()
        self.redrawAll()
        # print(f"Resized! {event.height}, {event.width}")

    def initGame(self):
        self.cardRects = []
        self.stackRects = []
        self.baseRect = None
        self.selected = (-1, -1)
        self.dragging = False
        self.mousePos = (0, 0)
        self.mousePosOld = (0, 0)
        self.hasWon = False
        self.tips = None

    def startGame(self):
        self.stage = GAME
        self.initGame()
        core = Core()
        self.core = core
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.startGame(self.config)

        if self.config.isProfessionalMode():
            self.config.profStart += 1
        self.config.totalStart += 1
        pass

    def quitGame(self):
        self.autoSave()
        self.stage = MENU
        self.core = None
        self.redrawAll()

    def loadGame(self):
        from tkinter import filedialog
        save = filedialog.askopenfilename(filetypes=[('save file', '.txt')])
        if save is None or len(save) == 0:
            return
        # print(save)
        try:
            core = loadGameFromFile(save)
        except Exception as e:
            print(e)
            return
        self.core = core
        self.stage = GAME
        self.initGame()
        self.updateRect()
        self.redrawAll()
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.resumeGame()

        # core.startGame(GameConfig.loadFromFile("config.ini"))
        pass

    def saveGame(self):
        from tkinter import filedialog
        import time
        initialName = "save_" + time.strftime("%Y-%m-%d_%H_%M", time.localtime()) + ".txt"
        save = filedialog.asksaveasfilename(filetypes=[('save file', '.txt')], initialfile=initialName)
        if save is None or len(save) == 0:
            return
        print(save)
        try:
            saveGameToFile(self.core, save)
        except Exception as e:
            print(e)

    def autoSave(self):
        try:
            if self.stage == GAME:
                self.config.gameOngoing = 1
                saveGameToFile(self.core, "autosave.txt")
        except Exception as e:
            print(e)

    def resumeAutoSave(self):
        if not self.config.isOngoing():
            return
        try:
            core = loadGameFromFile("autosave.txt")
        except Exception as e:
            print(e)
            return
        self.core = core
        self.stage = GAME
        self.initGame()
        self.updateRect()
        self.redrawAll()
        core.registerInterface(self)
        core.registerPlayer(DUMMY_PLAYER)
        core.resumeGame()

    def redrawAll(self):

        canvas = self.canvas
        canvas.delete(ALL)
        canvas.create_rectangle(0, 0, self.width, self.height,
                                fill='white', width=0)
        if self.stage == GAME:
            self.gameStageRedrawAll()
        elif self.stage == MENU:
            self.menuStageRedrawAll()
        elif self.stage == STATISTICS:
            self.statStageRedrawAll()
        canvas.update()
        pass

    def updateTips(self):
        if self.stage != GAME:
            return
        core = self.core
        if not core.existValidMove():
            self.tips = "You have no valid move!"
        else:
            self.tips = None
        pass

    def updateRect(self):
        if self.stage != GAME:
            return
        core = self.core
        width = self.width
        height = self.height
        cardWidth = self.cardWidth
        cardHeight = self.cardHeight
        selectedShowingHeight = int(cardHeight * SELECTED_SHOWING_HEIGHT_PERCENT)

        stackCount = len(core.stacks)
        yStart = 20
        xMargin = (width - stackCount * cardWidth) // (stackCount + 1)
        cardRects = [[] for _ in range(stackCount)]
        stackRects = []
        x = xMargin
        (ss, sn) = self.selected
        mainHeight = height - yStart - cardWidth - 10
        for i in range(stackCount):
            stack = cardRects[i]
            y = yStart
            stackRects.append(Rect((x, y), cardWidth, cardHeight))
            stackSize = len(core.stacks[i])
            dy = self.computeDeltaY(i == ss, stackSize, mainHeight)
            for j in range(stackSize):
                stack.append(Rect((x, y), cardWidth, cardHeight))
                if i == ss and j == sn:
                    y += selectedShowingHeight
                else:
                    y += dy
            x += cardWidth + xMargin
        self.cardRects = cardRects
        self.stackRects = stackRects
        self.updateDragging()

        baseRect = Rect((width - cardHeight - xMargin, height - cardWidth - 20), cardHeight, cardWidth)
        self.baseRect = baseRect
        pass

    def computeDeltaY(self, isSelected, stackSize, height):
        selectedShowingHeight = int(self.cardHeight * SELECTED_SHOWING_HEIGHT_PERCENT)
        notSelectedShowingHeight = int(self.cardHeight * NOT_SELECTED_SHOWING_HEIGHT_PERCENT)
        if stackSize < 2:
            return 0
        if isSelected:
            return min(notSelectedShowingHeight, (height - self.cardHeight - selectedShowingHeight) // (stackSize - 1))
        else:
            return min(notSelectedShowingHeight, (height - self.cardHeight) // stackSize)

    def updateDragging(self):
        if self.stage != GAME or self.hasWon or not self.dragging:
            return
        (x1, y1) = self.mousePosOld
        (x2, y2) = self.mousePos
        dx, dy = x2 - x1, y2 - y1
        rects = self.cardRects
        stack = rects[self.selected[0]]
        for i in range(self.selected[1], len(stack)):
            r = stack[i]
            (x, y) = r.upperLeft
            r.upperLeft = (x + dx, y + dy)

    def computeCardWidth(self):
        width = self.width
        height = self.height
        cardWidth = width * CARD_WIDTH_PERCENT
        cardHeight = height * CARD_HEIGHT_PERCENT
        if cardHeight >= cardWidth * CARD_HEIGHT_MULTIPLIER:
            cardHeight = cardWidth * CARD_HEIGHT_MULTIPLIER
        else:
            cardWidth = cardHeight / CARD_HEIGHT_MULTIPLIER
        self.cardHeight = cardHeight
        self.cardWidth = cardWidth
        self.updateRect()

    def gameStageRedrawAll(self):
        self.drawBase()
        core = self.core
        rects = self.cardRects
        canvas = self.canvas
        (si, sj) = self.selected
        for i in range(len(core.stacks)):
            stack = core.stacks[i]
            for j in range(len(stack)):
                if i == si and j == sj:
                    break
                rects[i][j].drawCard(canvas, stack[j])
        if 0 <= si < len(core.stacks):
            stack = core.stacks[si]
            for j in range(sj, len(stack)):
                rects[si][j].drawCard(canvas, stack[j])
        if self.hasWon:
            canvas = self.canvas
            canvas.create_text(self.width / 2, self.height / 2, text="You win!", font="Arial 30", anchor=CENTER)
            canvas.create_text(self.width / 2, self.height / 2 + 40, text="Press any key to return to main menu.",
                               font="Arial 10",
                               anchor=CENTER)
        else:
            if self.tips is not None:
                canvas.create_text(self.width / 2, self.height - 40, text=self.tips, font="Arial 25", anchor=CENTER)
        pass

    def drawBase(self):
        core = self.core
        canvas = self.canvas
        for re in self.stackRects:
            (x, y) = re.upperLeft
            canvas.create_rectangle(x, y, x + re.width, y + re.height, fill=None, outline="black")
        if len(core.base) > 0:
            br = self.baseRect
            (x, y) = br.upperLeft
            canvas.create_rectangle(x, y, x + br.width, y + br.height, fill=CARD_COLOR)
            canvas.create_text(x + 1, y, text=f"Remaining:\n {len(core.base)}", font="Arial 10", anchor=NW)
        canvas.create_text(10, self.height - 40, text=f"Finished piles: {core.finishedCount}", font="Arial 12",
                           anchor=W)

        if self.config.isProfessionalMode():
            txt = "[prof] undo: z, redo: x, restart: r, quit:q"
        else:
            txt = "undo: z, redo: x, restart: r, save: s, quit: q"
        canvas.create_text(10, self.height - 20, text=txt, anchor=W)
        pass

    def onWin(self):
        self.hasWon = True
        self.config.totalWin += 1
        if self.config.isProfessionalMode():
            self.config.profWin += 1
        self.config.gameOngoing = 0
        self.redrawAll()

    def menuStageRedrawAll(self):
        self.canvas.create_text(self.width / 2, 60, text="Spider Card Game", font="Arial 30", anchor=N)
        if self.config.isProfessionalMode():
            texts = ["[Professional Mode]"]
            if self.config.isOngoing():
                texts.append("Resume:(r)")
            else:
                texts.append("New Game:(n)")
        else:
            texts = []
            if self.config.isOngoing():
                texts.append("Resume:(r)")
            texts.append("New Game:(n)")
            texts.append("Load:(l)")
        texts.append("Statistics:(s)")
        y = 125
        for t in texts:
            self.canvas.create_text(self.width / 2, y, text=t, font="Arial 20", anchor=N)
            y += 50
        pass

    def statStageRedrawAll(self):
        self.canvas.create_text(self.width / 2, 60, text="Statistics:", font="Arial 30", anchor=N)
        config = self.config
        texts = ["Total Wins: " + str(config.totalWin),
                 "Total Games: " + str(config.totalStart),
                 "[Prof] Wins: " + str(config.profWin),
                 "[Prof] Games: " + str(config.profStart)]
        start = max(config.profStart, 1)
        winRate = float(config.profWin) / start
        texts.append("[Prof] Win Rate: " + format(winRate,"0.2f"))

        y = 150
        for t in texts:
            self.canvas.create_text(self.width / 2 - 100, y, text=t, font="Arial 15", anchor=W)
            y += 50

        self.canvas.create_text(self.width / 2, self.height - 50, text="press any key to return", font="Arial 15", anchor=N)
        pass

    def timerFiredWrapper(self):
        self.timerFired()
        self.canvas.after(self.timerDelay, self.timerFiredWrapper)

    def timerFired(self):
        pass

    def mousePressed(self, event):
        if self.stage != GAME:
            return
        if self.hasWon:
            return
        # print(f"Pressed at {event.x},{event.y}")
        x = event.x
        y = event.y

        rects = self.cardRects
        selected = None
        for i in range(len(rects)):
            stack = rects[i]
            toBreak = False
            for j in range(len(stack) - 1, -1, -1):
                re = stack[j]
                if re.contains(x, y):
                    selected = (i, j)
                    toBreak = True
                    break
            if toBreak:
                break
        if selected is None:
            self.checkClickBase(event)
            return
        self.selected = selected
        core = self.core
        if core.isValidSequence(selected):
            self.dragging = True
        self.mousePos = (x, y)
        self.mousePosOld = (x, y)
        # print("Selected!")
        self.updateRect()
        self.redrawAll()
        pass

    def checkClickBase(self, event):
        x = event.x
        y = event.y
        if not self.baseRect.contains(x, y):
            return
        self.core.askDeal()

    def mouseMoved(self, event):
        if self.stage != GAME:
            return
        if self.hasWon:
            return
        if not self.dragging:
            return
        # print(f"Moving at {event.x},{event.y}")
        temp = self.mousePos
        self.mousePosOld = temp
        self.mousePos = (event.x, event.y)
        self.updateDragging()
        self.redrawAll()
        pass

    def mouseReleased(self, event):
        if self.stage != GAME:
            return
        if self.hasWon:
            return
        # print("Released!")
        if self.dragging:
            self.dragging = False
            (si, sj) = self.selected
            rects = self.cardRects
            selectedRect = rects[si][sj]
            core = self.core
            dest = -1
            for i in range(len(core.stacks)):
                if i == si:
                    continue
                stack = rects[i]
                if len(stack) == 0:
                    top = self.stackRects[i]
                else:
                    top = lastOf(stack)
                if top.intersects(selectedRect):
                    dest = i
                    break
            self.core.askMove(self.selected, dest)
        self.selected = (-1, -1)
        self.updateRect()
        self.redrawAll()
        pass

    def keyPressed(self, event):
        if self.stage == GAME:
            self.gameKeyPressed(event)
        elif self.stage == MENU:
            self.menuKeyPressed(event)
        elif self.stage == STATISTICS:
            self.stage = MENU
            self.redrawAll()
        pass

    def menuKeyPressed(self, event):
        if event.char == "n":
            if self.config.isProfessionalMode() and self.config.isOngoing():
                self.resumeAutoSave()
            else:
                self.startGame()
        elif event.char == "l":
            self.loadGame()
        elif event.char == "r":
            self.resumeAutoSave()
        elif event.char == "s":
            self.stage = STATISTICS
            self.redrawAll()
        pass

    def gameKeyPressed(self, event):
        if self.hasWon:
            self.stage = MENU
            self.redrawAll()
            return
        if event.char == "z":
            self.core.askUndo()
            return
        elif event.char == "x":
            self.core.askRedo()
            return
        elif event.char == "r":
            if not messagebox.askokcancel("Quit", "Do you want to restart?"):
                return
            self.startGame()
        elif event.char == "s":
            if not self.config.isProfessionalMode():
                self.saveGame()
        elif event.char == "q":
            self.quitGame()
        pass

    def notifyRedraw(self):
        if self.stage != GAME:
            return
        self.updateTips()
        self.updateRect()
        self.canvas.after(0, self.redrawAll)


if __name__ == '__main__':
    interface = TkInterface(900, 600)
    interface.run()
