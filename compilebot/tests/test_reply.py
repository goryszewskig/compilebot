from __future__ import unicode_literals, print_function
import unittest
import random
import string 
from imp import reload
import compilebot as cb

"""
Unit test cases for functions, methods, and classes that format, create, 
and edit replies. All tests in this module shouldn't make any requests 
to reddit or ideone.

Run the following command from the parent directory in order to run only
this test module: python -m unittest tests.test_reply
"""

LOG_FILE = "tests.log" 
cb.LOG_FILE = LOG_FILE

def reddit_id(length=6):
    """Emulate a reddit id with a random string of letters and digits"""
    return ''.join(random.choice(string.ascii_lowercase + 
                   string.digits) for x in range(length))
    
def test_suite():
    cases = [
        TestParseComment, TestCreateReply, TestProcessUnread, TestDetectSpam
    ]
    alltests = [
        unittest.TestLoader().loadTestsFromTestCase(case) for case in cases
    ]
    return unittest.TestSuite(alltests)


class TestParseComment(unittest.TestCase):

    def setUp(self):
        self.user = cb.R_USERNAME

    def test_parser(self):
        body = ("This sentence should not be included. +/u/{user} python 3\n\n"
                "    print(\"Test\")\n\n"
                "This sentence should not be included.".format(user=self.user))
        args, source, stdin = cb.parse_comment(body)
        self.assertEqual(args, 'python 3')
        self.assertEqual(source, 'print(\"Test\")')
        self.assertEqual(stdin, '')
    
    def test_parse_args(self):
        body = ("+/u/{user} python 3 --time\n\n"
                "    \n        x = input()\n    print(\"x\")\n    \n\n\n"
                "Input: \n\n    5\n    6\n    7").format(user=self.user)
        args, source, stdin = cb.parse_comment(body)
        self.assertEqual(args, 'python 3 --time')
        self.assertEqual(source, '    x = input()\nprint(\"x\")\n')
        self.assertEqual(stdin, '5\n6\n7')
        
    def test_errors(self):
        # Should raise an attribute error when there an indented code
        # block is missing.
        body = ("+/u/{user} Java\n\n Source code missing"
                "\n\n".format(user=self.user))
        self.assertRaises(AttributeError, cb.parse_comment, (body))

class TestCreateReply(unittest.TestCase):
    
    # Simplified version of a PRAW comment for testing purposes.
    class Comment(object):
        def __init__(self, body):
            self.body = body
            self.id = reddit_id()
            self.permalink = ''
    
    def setUp(self):
        self.user = cb.R_USERNAME
    
    def test_create_reply(self):
        def compile(*args, **kwargs):
            return {
                'cmpinfo': "",
                'input': "",
                'langName': "Python",
                'output': "Test",
                'result': 15,
                'stderr': "",
                'link': ""
            }
        cb.compile = compile
        body = ("+/u/{user} python\n\n"
                "    print(\"Test\")\n\n".format(user=self.user))
        comment = self.Comment(body)
        reply = cb.create_reply(comment)
        self.assertIn("Output:\n\n    Test\n", reply.text)
        
    def test_bad_format(self):
        body = "+/u/{user} Formatted incorrectly".format(user=self.user)
        comment = self.Comment(body)
        reply = cb.create_reply(comment)
        self.assertIsInstance(reply, cb.MessageReply)
        self.assertIn(cb.FORMAT_ERROR_TEXT, reply.text)
        
    def test_missing_language(self):
        def compile(*args, **kwargs):
            raise cb.ideone.LanguageNotFoundError(error_msg, similar_langs)
        cb.compile = compile
        error_msg = "Language Error Message"
        similar_langs = ["FooBar", "BazzScript", "Z 1-X"]
        # When the compile function returns an LanguageNotFoundError,
        # compilebot should notify the user the possible languages they 
        # were looking for via message reply.
        body = "+/u/{user} Foo\n\n    print(\"Test\")\n\n".format(user=self.user)
        comment = self.Comment(body)
        reply = cb.create_reply(comment)
        self.assertIsInstance(reply, cb.MessageReply)
        self.assertTrue(all(lang in reply.text for lang in similar_langs))
        
    def test_result_errors(self):
        # Test each error code and ensure the user will be alerted of
        # errors via private message instead of in compiled replies.
        for error_code in [13, 17, 19, 20, 12]:
            def compile(*args, **kwargs):
                return {
                    'cmpinfo': "",
                    'input': "",
                    'langName': "Python",
                    'output': "Test",
                    'result': error_code,
                    'stderr': "Error message",
                    'link': ""
                }
            cb.compile = compile
            body = ("+/u/{user} python\n\n"
                    "    error\n\n".format(user=self.user))
            comment = self.Comment(body)
            reply = cb.create_reply(comment)
            self.assertIsInstance(reply, cb.MessageReply)
        body = ("+/u/{user} python --include-errors\n\n"
                "    error\n\n".format(user=self.user))
        comment = self.Comment(body)
        reply = cb.create_reply(comment)
        self.assertIsInstance(reply, cb.CompiledReply)
        
    def tearDown(self):
        reload(cb)
        cb.LOG_FILE = LOG_FILE

class TestProcessUnread(unittest.TestCase):
    
    # The following classes are meant to emulate various PRAW objects
    # They do not contain all of the same attributes if the original
    # PRAW class, but only the necessary ones needed for testing the
    # process_unread function.
    
    class Reddit(object):
        def __init__(self):
            self._sent_message = False
            self._message_recipient = ''
            self._message_subject = ''
            self._message_text = ''
            # Allows a custom comment to be assigned that is used to
            # verify if get_submission is working correctly.
            self._get_sub_comment = None
            
        def get_subreddit(*args, **kwargs):
            pass
            
        def send_message(self, recipient, subject, text, **kwargs):
            self._sent_message = True
            self._message_recipient = recipient
            self._message_subject = subject
            self._message_text = text
            
        def get_submission(self, *args, **kwargs):
            s = TestProcessUnread.Submission()
            if kwargs.get('submission_id') == self._get_sub_comment.permalink:
                s.comments.append(self._get_sub_comment)
            return s
    
    class Submission(object):
        def __init__(self):
            self.comments = []
            
    class Repliable(object):
        def __init__(self, author=None, body='', reddit_session=None, replies=[]):
            self.author = author or TestProcessUnread.Author()
            self.body = body
            self.replies = replies
            self.id = reddit_id()
            self.reddit_session = reddit_session
            self._replied_to = False
            self._reply_text = ''    
        
        def reply(self, text):
            self._replied_to = True
            self._reply_text = text
    
    class Author(object):
        def __init__(self, name=''):
            self.name = name
            
        def __eq__(self, other):
            return self.name == other.name
            
        def __ne__(self, other):
            return self.name != other.name
            
        def __str__(self):
            return self.name
            
    class Message(Repliable):
        def __init__(self, *args,  **kwargs):
            TestProcessUnread.Repliable.__init__(self, *args, **kwargs)
            self.was_comment = False
            
    class Comment(Repliable):
        def __init__(self, *args, **kwargs):
            TestProcessUnread.Repliable.__init__(self, *args, **kwargs)
            self.was_comment = True
            self.permalink = reddit_id() + '/test/' + self.id
            self._edited = False
            self._edit_text = ''
            
        def edit(self, text):
            self._edited = True
            self._edit_text = text
    
    def setUp(self):
        self.r = self.Reddit()
        self.user = cb.R_USERNAME
         
    def test_process_reply(self):
    
        def compile(*args, **kwargs):
            return {
                'cmpinfo': '', 'error': 'OK', 'input': "Hello World",
                'langId': 116, 'link': '', 'langName': "Python 3",
                'output': "Hello World\n", 'public': True, 'result': 15,
                'signal': 0, 'source': "x = input()\nprint(x)", 'status': 0,
                'stderr': "",
            }
        
        cb.compile = compile
        body = ("+/u/{user} python 3\n\n    x = input()\n    print(x)"
                "\n\n".format(user=self.user))
        new = self.Comment(body=body, reddit_session=self.r)
        cb.process_unread(new, self.r)
        self.assertTrue(new._replied_to)
        self.assertIn("Output:\n\n    Hello World", new._reply_text)
        
    def test_help_request(self):
        new = self.Message(body="--help", reddit_session=self.r)
        cb.process_unread(new, self.r)
        self.assertTrue(self.r._sent_message)
        self.assertIn(cb.HELP_TEXT, self.r._message_text)
        
    def test_banned_filter(self):
        cb.BANNED_USERS.add("Banned-User-01")
        new = self.Comment(author=self.Author(name="Banned-User-01"))
        cb.process_unread(new, self.r)
        self.assertFalse(new._replied_to)
        
    def test_recompile_request(self):
    
        def compile(*args, **kwargs):
            return {
                'cmpinfo': '', 'error': 'OK', 'input': "Hello World",
                'langId': 116, 'link': '', 'langName': "Python 3",
                'output': "Hello World\n", 'public': True, 'result': 15,
                'signal': 0, 'source': "x = input()\nprint(x)", 'status': 0,
                'stderr': "",
            }
        
        cb.compile = compile
        # Create the comment that will be recompiled.    
        body = ("+/u/{user} python 3\n\n    x = input()\n    print(x)"
                "\n\n".format(user=self.user))
        original = self.Comment(body=body, reddit_session=self.r)
        self.r._get_sub_comment = original
        # Message that makes the recompile request.
        body = "--recompile {link}".format(link=original.permalink)
        new = self.Message(body=body, reddit_session=self.r)
        cb.process_unread(new, self.r)
        self.assertTrue(original._replied_to)
        
    def test_recompile_edit(self):
        # Ensure that if there is an existing reply from a bot on a 
        # comment that is being recompiled, the existing reply is 
        # editing instead of making a new comment.
        def compile(*args, **kwargs):
            return {
                'cmpinfo': '', 'error': 'OK', 'input': "Hello World",
                'langId': 116, 'link': '', 'langName': "Python 3",
                'output': "Test\n", 'public': True, 'result': 15,
                'signal': 0, 'source': "print(\"Test\")", 'status': 0,
                'stderr': "",
            }
            
        cb.compile = compile
        existing_reply = self.Comment(author=self.Author(self.user))
        body = ("+/u/{user} python 3\n\n    print(\"test\")\n\n"
               "\n\n".format(user=self.user))
        
        replies = [existing_reply]
        original = self.Comment(body=body, reddit_session=self.r, 
                                replies=replies)
        self.r._get_sub_comment = original
        
        body = "--recompile {link}".format(link=original.permalink)
        new = self.Message(body=body, reddit_session=self.r)
        cb.process_unread(new, self.r)
        self.assertTrue(existing_reply._edited)
        self.assertIn("Output:\n\n    Test", existing_reply._edit_text)
        self.assertFalse(original._replied_to)
    
    def test_recompile_user_permissions(self):
        # Ensure users aren't allowed to make recompile requests of behalf
        # of other users.
        original = self.Comment(reddit_session=self.r, 
                                author=self.Author("Author-1"))
        self.r._get_sub_comment = original
        body = "--recompile {link}".format(link=original.permalink)
        new = self.Message(body=body, reddit_session=self.r, 
                           author=self.Author("Author-2"))
        cb.process_unread(new, self.r)
        self.assertFalse(original._replied_to)
        self.assertTrue(new._replied_to)
        
    def tearDown(self):
        reload(cb)
        cb.LOG_FILE = LOG_FILE
        
class TestDetectSpam(unittest.TestCase):
    
    class Comment(object):
        def __init__(self):
            self.author = ''
            self.permalink = ''
    
    def create_reply(self, spam):
        details = {
            'output': spam,
            'source': '',
            'stderr': ''
        }
        text = "Output:\n\n\n{}\n".format(spam)
        reply = cb.CompiledReply(text, details)
        reply.parent_comment = self.Comment()
        return reply
        
    def test_line_breaks(self):
        spam = "    \n" * (cb.LINE_LIMIT + 1)
        reply = self.create_reply(spam)
        self.assertIn("Excessive line breaks", reply.detect_spam())
        
    def test_char_limit(self):
        spam = "a" * (cb.CHAR_LIMIT + 1)
        reply = self.create_reply(spam)
        self.assertIn("Excessive character count", reply.detect_spam())
       
    def test_spam_phrases(self):
        spam = "Spam Phrase"
        cb.SPAM_PHRASES.append(spam)
        reply = self.create_reply(spam)
        self.assertIn("Spam phrase detected", reply.detect_spam())
        
    def test_permission_denied(self):
        spam = ""
        reply = self.create_reply(spam)
        reply.compile_details['stderr'] = "'rm -rf /*': Permission denied"
        self.assertIn("Illegal system call detected", reply.detect_spam())

     
if __name__ == "__main__":
    unittest.main(exit=False)
