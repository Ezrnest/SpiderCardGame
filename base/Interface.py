from base.Core import Core, GameEvent


class Interface:

    def __init__(self):
        self.core: Core = None

    def onStart(self):
        pass

    def onEvent(self, event: GameEvent):
        """
        Invoked when a game event is performed.
        :param event:
        :return:
        """
        self.notifyRedraw()
        pass

    def onUndoEvent(self, event: GameEvent):
        """
        Invoked when a game event is undone.
        :param event:
        :return:
        """
        self.notifyRedraw()
        pass

    def notifyRedraw(self):
        pass

    def onWin(self):
        pass
