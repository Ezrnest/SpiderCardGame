import random

DUMMY_PLAYER = "Dummy"


def ceilDiv(x, y):
    return (x + y - 1) // y


def lastOf(lst):
    return lst[len(lst) - 1]


class Card:
    NUM_PER_SUIT = 13
    SUITS = "♠♥♣♦"  # ♦Q  ♠7  ♣7  ♥5  ♥9
    # SUITS = "MHGD"
    NUMS = ("A ", "2 ", "3 ", "4 ", "5 ", "6 ", "7 ", "8 ", "9 ", "10", "J ", "Q ", "K ")

    def __init__(self, id):
        self.id = id
        self.suit = self.__suit()
        self.num = self.__num()
        self.hidden = True

    def __suit(self):
        return self.id // Card.NUM_PER_SUIT

    def __num(self):
        return self.id % Card.NUM_PER_SUIT

    def __str__(self):
        if self.hidden:
            return str(self.id) + "H"
        return str(self.id)

    def __repr__(self):
        return self.__str__()

    def gameStr(self):
        if self.hidden:
            return "---"
        if -1 < self.id < 52:
            return Card.SUITS[self.suit] + Card.NUMS[self.num]
        return str(self.id)

    def color(self):
        if self.suit % 2 == 0:
            return "black"
        else:
            return "red"

    def suitableAsBaseFor(self, upper):
        return self.num == upper.num + 1

    def suitableAsSequenceFor(self, upper):
        return self.suit == upper.suit and self.num == upper.num + 1

    @staticmethod
    def fromSuitAndNum(suit, num):
        return Card(suit * Card.NUM_PER_SUIT + num)

    @staticmethod
    def extendStack(stack, suit, hidden=True):
        base = suit * Card.NUM_PER_SUIT
        for i in range(Card.NUM_PER_SUIT - 1, -1, -1):
            cd = Card(base + i)
            cd.hidden = hidden
            stack.append(cd)


DUMMY_CARD = Card(0)


def initCards(suits, pileCount):
    lst = []
    for i in range(suits):
        remainCount = suits - i
        count = ceilDiv(pileCount, remainCount)  # ceil divide
        pileCount -= count
        for n in range(Card.NUM_PER_SUIT):
            for _ in range(count):
                lst.append(Card.fromSuitAndNum(i, n))
    random.shuffle(lst)
    return lst


def decodeStack(code: str):
    if code.startswith("empty"):
        return []
    cards = code.split(",")

    def decodeCard(s: str):
        data = s.split(" ")
        cardId = int(data[0])
        hidden = data[1] == "1"
        c = Card(cardId)
        c.hidden = hidden
        return c

    return list(map(decodeCard, cards))


def encodeStack(base: list):
    if len(base) == 0:
        return "empty"
    def encodeCard(card: Card):
        s = str(card.id)
        if card.hidden:
            return s + " 1"
        else:
            return s + " 0"

    return ",".join(map(encodeCard, base))


class GameConfig:
    def __init__(self):
        self.suits = 4
        self.piles = 8
        self.stackCount = 10
        self.initialDealt = 54
        self.gameCode = None
        self.professionalMode = 0
        self.profStart = 0
        self.profWin = 0
        self.gameOngoing = 0
        self.totalWin = 0
        self.totalStart = 0
        # self.

    def isProfessionalMode(self):
        return self.professionalMode == 1

    def isOngoing(self):
        return self.gameOngoing == 1

    @staticmethod
    def loadFromFile(path):
        try:
            f = open(path)
            lines = f.readlines()
            f.close()
            config = GameConfig()
            for l in lines:
                if len(l) == 0:
                    continue
                if l.startswith("#"):
                    continue
                (k, v) = l.split("=")
                k = k.strip()
                v = v.strip()
                try:
                    v = int(v)
                except:
                    pass
                config.__setattr__(k, v)
            return config
        except:
            return GameConfig()


    def saveToFile(self, path):
        with open(path,"w+") as f:
            for k,v in self.__dict__.items():
                f.write(f"{k}={str(v)}\n")


    def initBase(self):
        if self.gameCode is not None:
            try:
                return decodeStack(self.gameCode)
            except:
                pass
        return initCards(self.suits, self.piles)


class GameEvent:
    def perform(self, core):
        pass

    def undo(self, core):
        pass

    def isAuto(self) -> bool:
        return False


class CardMove(GameEvent):
    def __init__(self, src: (int, int), dest: (int, int)):
        self.src = src
        self.dest = dest

    pass

    def undo(self, core):
        # core
        core.undoMove(self)
        pass

    def perform(self, core):
        core.doMove(self.src, self.dest[0], False)
        pass


class CallDeal(GameEvent):
    def __init__(self, drawCount: int):
        self.drawCount = drawCount
        pass

    def undo(self, core):
        core.undoDeal(self)

    def perform(self, core):
        core.doDeal(self.drawCount, False)


class FreeStack(GameEvent):
    def __init__(self, idx, suit):
        self.idx = idx
        self.suit = suit

    def undo(self, core):
        core.undoFree(self)
        pass

    def perform(self, core):
        core.doFree(self.idx, False)
        pass

    def isAuto(self):
        return True


class RevealTop(GameEvent):
    def __init__(self, idx):
        self.idx = idx

    def undo(self, core):
        core.undoReveal(self)
        pass

    def perform(self, core):
        core.doReveal(self.idx, False)

    def isAuto(self):
        return True


class Core:
    """
    ask*** : should be called by "player"
    do*** : actual operation, no doing other things.
    """
    DEFAULT_CONFIG = GameConfig()

    def __init__(self):
        self.interface = None
        self.player = None

        self.base = None  # base cards piles
        self.stacks = None  # the stacks of the cards that the player mainly operate on, a list of lists
        self.finishedCount = None
        self.gameEnded = None

        self.history: HistoryRecorder = None
        pass

    def registerInterface(self, interface):
        self.interface = interface
        interface.core = self

    def registerPlayer(self, player):
        self.player = player

    def startGame(self, gameConfig: GameConfig = DEFAULT_CONFIG):
        if self.interface is None or self.player is None:
            raise Exception("interface or player is null")
        self.base = gameConfig.initBase()
        self.stacks = [[] for _ in range(gameConfig.stackCount)]
        self.finishedCount = 0

        self.history = HistoryRecorder(self)
        self.gameEnded = False
        self.interface.onStart()
        self.doDeal(gameConfig.initialDealt, False)
        pass

    def resumeGame(self):
        if self.interface is None or self.player is None:
            raise Exception("interface or player is null")
        self.interface.onStart()

    def checkWin(self):
        if len(self.base) != 0:
            return False
        for stack in self.stacks:
            if len(stack) != 0:
                return False
        self.gameEnded = True
        self.interface.onWin()
        return True

    def canMove(self, src, dest: int):
        if not self.isValidSequence(src):
            return False
        (s1, idx1) = src
        if dest < 0 or dest >= len(self.stacks):
            return False
        idx2 = len(self.stacks[dest]) - 1
        if idx2 == -1:  # empty
            return True
        sequenceBase = self.stacks[s1][idx1]
        base = self.stacks[dest][idx2]
        return base.num == sequenceBase.num + 1

    def existValidMove(self):
        for stack in self.stacks:
            if len(stack) == 0:
                continue
            idx = len(stack) - 1
            top = stack[idx]
            if top.hidden is True:
                return True
            if self.existValidDestination(top):
                return True
            while idx > 0:
                idx -= 1
                base = stack[idx]
                if base.hidden is True or (not base.suitableAsSequenceFor(top)):
                    break
                if self.existValidDestination(base):
                    return True
                top = base

        return False

    def existValidDestination(self, card):
        for stack in self.stacks:
            if len(stack) == 0:
                return True
            if stack[len(stack) - 1].suitableAsBaseFor(card):
                return True
        return False

    def isValidPosition(self, s, idx):
        if s < 0 or s >= len(self.stacks):
            return False
        stack = self.stacks[s]
        if idx < 0 or idx >= len(stack):
            return False
        return True

    def isValidSequence(self, src):
        """

        :param src: a pair of (index of stack, index of the start of the sequence)
        :return:
        """
        (s, idx) = src
        if not self.isValidPosition(s, idx):
            return False
        stack = self.stacks[s]
        return Core.__isValidSequence0(stack, idx)

    @staticmethod
    def __isValidSequence0(stack, idx):
        base = stack[idx]
        if base.hidden:
            return False
        for i in range(idx + 1, len(stack)):
            upper = stack[i]
            if not (base.suit == upper.suit and base.num == upper.num + 1):
                return False
            base = upper
        return True

    def askMove(self, src: (int, int), dest: int) -> bool:
        if not self.canMove(src, dest):
            return False
        self.doMove(src, dest, True)
        self.doReveal(src[0], True)
        self.askFree(dest)
        return True

    def askFree(self, dest: int):
        self.doFree(dest, True)
        self.doReveal(dest, True)
        self.checkWin()

    def askDeal(self) -> bool:
        count = min(len(self.stacks), len(self.base))
        if count > 0:
            self.doDeal(count, True)
            return True
        return False

    def askUndo(self):
        return self.history.undo()

    def askRedo(self):
        return self.history.redo()

    def doMove(self, src: (int, int), dest: int, doLog=True):
        stacks = self.stacks
        srcStack = stacks[src[0]]
        newSrcStack = srcStack[:src[1]]
        temp = srcStack[src[1]:]
        destStack = stacks[dest]
        destPair = (dest, len(destStack))
        stacks[src[0]] = newSrcStack
        destStack.extend(temp)

        event = CardMove(src, destPair)
        if doLog:
            self.history.log(event)
        self.interface.onEvent(event)

    @staticmethod
    def __setTopVisible(stack):
        if len(stack) > 0:
            stack[len(stack) - 1].hidden = False

    def doFree(self, dest: int, doLog=True):
        stack = self.stacks[dest]
        length = len(stack)
        suit = stack[length - 1].suit
        for i in range(Card.NUM_PER_SUIT):
            card = stack[length - i - 1]
            if card.suit != suit or card.num != i:
                return -1

        self.stacks[dest] = stack[:(length - Card.NUM_PER_SUIT)]
        self.finishedCount += 1
        event = FreeStack(dest, suit)
        if doLog:
            self.history.log(event)
        self.interface.onEvent(event)
        return suit

    def doReveal(self, idx: int, doLog=True):
        if idx < 0 or idx >= len(self.stacks):
            return False
        if len(self.stacks[idx]) == 0:
            return False
        card = lastOf(self.stacks[idx])
        if not card.hidden:
            return False
        card.hidden = False
        event = RevealTop(idx)
        if doLog:
            self.history.log(event)
        self.interface.onEvent(event)
        return True

    def doDeal(self, drawCount, doLog=True):
        stacks = self.stacks
        base = self.base
        stackCount = len(stacks)
        drawCount = min(drawCount, len(base))
        event = CallDeal(drawCount)
        dest = 0
        while drawCount > 0:
            stacks[dest].append(base.pop())
            dest += 1
            if dest >= stackCount:
                dest = 0
            drawCount -= 1
        for s in self.stacks:
            self.__setTopVisible(s)
        if doLog:
            self.history.log(event)
        self.interface.onEvent(event)

    def undoMove(self, event: CardMove):
        src = event.src
        dest = event.dest
        destStack = self.stacks[dest[0]]
        srcStack = self.stacks[src[0]]
        self.stacks[dest[0]] = destStack[:dest[1]]
        for i in range(dest[1], len(destStack)):
            srcStack.append(destStack[i])
        self.interface.onUndoEvent(event)
        pass

    def undoDeal(self, event: CallDeal):
        count = event.drawCount
        stacks = self.stacks
        base = self.base
        i = (count - 1) % len(stacks)
        while count > 0:
            count -= 1
            card = stacks[i].pop()
            card.hidden = True
            base.append(card)
            i -= 1
            if i < 0:
                i += len(stacks)
        self.interface.onUndoEvent(event)
        pass

    def undoFree(self, event: FreeStack):
        stack = self.stacks[event.idx]
        Card.extendStack(stack, event.suit, False)
        self.finishedCount -= 1
        self.interface.onUndoEvent(event)
        pass

    def undoReveal(self, event: RevealTop):
        stack = self.stacks[event.idx]
        lastOf(stack).hidden = True
        self.interface.onUndoEvent(event)
        pass

    def saveGameAsLines(self):
        # self.

        """
        self.base = None  # base cards piles
        self.stacks = None # the stacks of the cards that the player mainly operate on, a list of lists
        self.finishedCount = None
        self.gameEnded = None

        self.history: HistoryRecorder = None

        """
        lines = []
        # base part
        lines.append(str(self.finishedCount))
        lines.append(str(self.gameEnded))
        lines.append(encodeStack(self.base))
        for stack in self.stacks:
            lines.append(encodeStack(stack))
        return lines

    def loadGameFromLines(self, lines):
        def lineFilter(s: str):
            return not s.isspace() and not s.startswith("#")

        lines = list(filter(lineFilter, lines))
        self.finishedCount = int(lines[0])
        self.gameEnded = bool(lines[1])
        self.base = decodeStack(lines[2])
        stacks = []
        for line in lines[3:]:
            stacks.append(decodeStack(line))
        self.stacks = stacks
        self.history = HistoryRecorder(self)
        pass


def saveGameToFile(core: Core, path):
    import time
    with open(path, "w+") as f:
        dateInfo = "# date: " + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()) + "\n"
        f.write(dateInfo)
        f.writelines([x + "\n" for x in core.saveGameAsLines()])


def loadGameFromFile(path):
    with open(path, "r+") as f:
        lines = f.readlines()
        core = Core()
        core.loadGameFromLines(lines)
        return core


class HistoryRecorder:
    def __init__(self, core):
        self.core = core
        self.lst = []
        self.idx = 0  # idx - 1 is equal to the index of next operation to be undo

    def __preLog(self):
        if self.idx != len(self.lst):
            self.lst = self.lst[:self.idx]
        self.idx += 1

    def log(self, event):
        self.__preLog()
        self.lst.append(event)

    def undo(self):
        idx = self.idx - 1
        lst = self.lst
        if idx < 0 or idx >= len(lst):
            return False
        while idx >= 0:
            event = lst[idx]
            event.undo(self.core)
            if not event.isAuto():
                break
            idx -= 1
        self.idx = idx
        return True

    def redo(self):
        idx = self.idx
        lst = self.lst
        if idx < 0 or idx >= len(lst):
            return False
        has = False
        while idx < len(lst):
            event = lst[idx]
            if not event.isAuto():
                if has:
                    break
                has = True
            event.perform(self.core)
            idx += 1
        self.idx = idx
        return True


class GenerateConfig:
    def __init__(self, basicSteps=10):
        self.basicSteps = 10
        self.freeProb = 10
        self.dealProb = 8
        self.moveProb = 400


def genFinished(suits, piles):
    lst = []
    for i in range(suits):
        count = ceilDiv(piles, suits - i)
        piles -= count
        for _ in range(count):
            lst += i
    random.shuffle(lst)
    return lst


def generateSolvable(config: GameConfig, gc: GenerateConfig):
    finished = genFinished(config.suits, config.piles)
    stacks = [[] for _ in range(config.stackCount)]
    base = []
    i = 0
    while i < gc.basicSteps:
        i += 1
        doStep(finished, stacks, config)


def doStep(finished, stacks, config):
    pass


def doMove(finished):
    pass
