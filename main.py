from game.ui.ui_manager import UIManager
from game.engine import GameEngine

def main():
    """Main entry point for the game."""
    ui = UIManager()
    engine = GameEngine(ui)
    engine.run()

if __name__ == "__main__":
    main()