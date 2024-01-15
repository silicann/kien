from kien import CommandResult, create_commander
from kien.test_helpers import KienTest


class SimpleKienTest(KienTest):
    commander = create_commander("simple test commander")

    @commander("anything")
    def command_anything():
        message = "There is really nothing to see."
        yield CommandResult(message, {"message": message})

    @commander("something")
    def command_something():
        message = "There is really more to see."
        yield CommandResult(message, {"message": message})

    def test_anything(self):
        response = self.get_response("anything")
        self.assertIn("nothing", response)
        response = self.get_response("something")
        self.assertIn("more", response)
