# -*- coding: utf-8 -*-


"""
CommandOptionParser HOWTO
=========================

1) setup CommandContainer
-------------------------
# In case you don't need any special functionality, just import default CommandContainer.
# Otherwise it's recommended to inherit your own container and extend it's functionality.
# Typical use cases are shared configuration or shared XML-RPC connection.

from kobo.cli import CommandContainer
class MyCommandContainer(CommandContainer):
    def __init__(self, *args, **kwargs):
        CommandContainer.__init__(self, *args, **kwargs)
        self.xmlrpc_client = ...


2) write your own Commands
--------------------------
# It usually makes sense to inherit directly from Command class.
# All common methods and attributes should be in the container.
# Specify any OptionParser options in options() method.
# OptionParser.parse_args() result is automatically passed to run(*args, **kwargs) method.
# A OptionParser instance os available in self.parser attribute.

class Make_Dirs(Command):
    '''create directories'''
    enabled = True
    admin = False

    def options(self):
        self.parser.usage = "%%prog %s [options] <user>" % self.normalized_name
        self.parser.add_option("-m", "--mode", help="set directory perms (0xxx)")

    def run(self, *args, **kwargs):
        if len(args) < 1:
            self.parser.error("Please specify a directory")
        mode = kwargs.pop("mode", "0755")
        mode = int(mode, 0) # convert oct string to int

        import os
        for directory in args:
            os.makedirs(directory, mode=mode)


3) register commands to a container
-----------------------------------
# Register either either all plugins (register_plugin)
# or all plugins in a module (register_module) to a container.
# All plugins must have enabled=True otherwise they won't be registered.

(My)CommandContainer.register_plugin(plugin_class)
(My)CommandContainer.register_module(module_with_plugins)


4) Use CommandOptionParser
--------------------------
command_container = (My)CommandContainer()
parser = CommandOptionParser(command_container=command_container)
parser.run()

# See kobo.client.main for slightly advanced example.
"""


import sys
import optparse
import datetime
from optparse import Option
from xmlrpclib import Fault

from kobo.plugins import Plugin, PluginContainer
from kobo.shortcuts import force_list

import os.path

__all__ = (
    "Command",
    "CommandContainer",
    "CommandOptionParser",
    "Option",
    "username_prompt",
    "password_prompt",
    "yes_no_prompt",
    "are_you_sure_prompt",
)


def username_prompt(prompt=None, default_value=None):
    """Ask for a username."""
    if default_value is not None:
        return default_value

    prompt = prompt or "Enter your username: "
    print >>sys.stderr, prompt,
    return sys.stdin.readline()


def password_prompt(prompt=None, default_value=None):
    """Ask for a password."""
    import getpass

    if default_value is not None:
        return default_value

    prompt = prompt or "Enter your password: "
    try:
        # try to use stderr stream
        result = getpass.getpass(prompt, stream=sys.stderr)
    except TypeError:
        # fall back to stdout
        result = getpass.getpass(prompt)
    return result


def yes_no_prompt(prompt, default_value=None):
    """Give a yes/no (y/n) question."""
    if default_value is not None:
        if default_value not in ("Y", "N"):
            raise ValueError("Invalid default value: %s" % default_value)
        default_value = default_value.upper()

    prompt = "%s [%s/%s]: " % (prompt, ("y", "Y")[default_value == "Y"], ("n", "N")[default_value == "N"])
    print >>sys.stderr, prompt,

    while True:
        user_input = sys.stdin.readline().strip().upper()
        if user_input == "" and default_value is not None:
            user_input = default_value

        if user_input == "Y":
            return True
        if user_input == "N":
            return False


def are_you_sure_prompt(prompt=None):
    """Give a yes/no (y/n) question."""
    prompt = prompt or "Are you sure? Enter 'YES' to continue: "
    print >>sys.stderr, prompt,
    user_input = sys.stdin.readline().strip()

    if user_input == "YES":
        return True

    return False


class Command(Plugin):
    """An abstract class representing a command for CommandOptionParser."""

    enabled = False
    admin = False

    username_prompt = staticmethod(username_prompt)
    password_prompt = staticmethod(password_prompt)
    yes_no_prompt = staticmethod(yes_no_prompt)
    are_you_sure_prompt = staticmethod(are_you_sure_prompt)

    def __init__(self, parser):
        Plugin.__init__(self)
        self.parser = parser

    def options(self):
        """Add options to self.parser."""
        pass

    def run(self, *args, **kwargs):
        """Run a command. Arguments contain parsed options."""
        raise NotImplementedError()


class CommandContainer(PluginContainer):
    """Container for Command classes."""

    @classmethod
    def normalize_name(cls, name):
        """Replace some characters in command names."""
        return name.lower().replace('_', '-').replace(' ', '-')


class CommandOptionParser(optparse.OptionParser):
    """Enhanced OptionParser with plugin support."""
    def __init__(self,
            usage=None,
            option_list=None,
            option_class=Option,
            version=None,
            conflict_handler="error",
            description=None,
            formatter=None,
            add_help_option=True,
            prog=None,
            command_container=None,
            default_command="help",
            add_username_password_options=False,
            default_profile="",
            configuration_directory="/etc"):

        usage = usage or "%prog <command> [args] [--help]"
        self.container = command_container
        self.default_command = default_command
        self.command = None
        formatter = formatter or optparse.IndentedHelpFormatter(max_help_position=33)

        optparse.OptionParser.__init__(self, usage, option_list, option_class, version, conflict_handler, description, formatter, add_help_option, prog)

        if add_username_password_options:
            self._add_opts(
                ["--username", "specify user"],
                ["--password", "specify password"]
            )

        if default_profile:
            self.default_profile = default_profile

            self._add_opts(
                ["--profile", "specify profile (default: {0})".format(self.default_profile)]
            )
        else:
            self.default_profile = ""

        self.configuration_directory = configuration_directory

    def print_help(self, file=None, admin=False):
        if file is None:
            file = sys.stdout
        file.write(self.format_help())
        if self.command in (None, "help", "help-admin"):
            file.write("\n")
            file.write(self.format_help_commands(admin=admin))

    def format_help_commands(self, admin=False):
        commands = []
        admin_commands = []

        for name, plugin in sorted(self.container.plugins.iteritems()):
            is_admin = getattr(plugin, "admin", False)
            text = "  %-30s %s" % (name, plugin.__doc__ or "")
            if is_admin:
                if admin:
                    admin_commands.append(text)
            else:
                commands.append(text)

        if commands:
            commands.insert(0, "commands:")
            commands.append("")

        if admin_commands:
            admin_commands.insert(0, "admin commands:")
            admin_commands.append("")

        return "\n".join(commands + admin_commands)

    def parse_args(self, args=None, values=None):
        """return (command_instance, opts, args)"""
        args = self._get_args(args)
        command = None

        if len(args) > 0 and not args[0].startswith("-"):
            command = args[0]
            args = args[1:]
        else:
            command = self.default_command
            # keep args as is

        if not command in self.container.plugins:
            self.error("unknown command: %s" % command)

        CommandClass = self.container[command]
        cmd = CommandClass(self)
        if self.command != cmd.normalized_name:
            self.command = cmd.normalized_name
            cmd.options()
        cmd_opts, cmd_args = optparse.OptionParser.parse_args(self, args, values)
        return (cmd, cmd_opts, cmd_args)

    def run(self, args=None, values=None):
        """parse arguments and run a command"""
        cmd, cmd_opts, cmd_args = self.parse_args(args, values)
        cmd_kwargs = cmd_opts.__dict__

        # this block should only be evaluated if default_profile has been set at instantiation
        if 'profile' in cmd_kwargs:
          self._load_profile(cmd_kwargs['profile'])

        cmd.run(*cmd_args, **cmd_kwargs)

    def _add_opts(self, *args):
        """populates one or more options with their respective help texts"""
        option_list = [optparse.Option(option, help=help_text) for option, help_text in args]

        self._populate_option_list(option_list=option_list, add_help=False)

    def _load_profile(self, profile):
        """load configuration file under location <CONFIGURATION_DIRECTORY>/<PROFILE>.conf"""
        if not profile:
            profile = self.default_profile

        configuration_file = os.path.join(self.configuration_directory, '{0}.conf'.format(profile))
        self.container.conf.load_from_file(configuration_file)

class Help(Command):
    """show this help message and exit"""
    enabled = True

    def options(self):
        pass

    def run(self, *args, **kwargs):
        self.parser.print_help(admin=False)


class Help_Admin(Command):
    """show help message about administrative commands and exit"""
    enabled = True

    def options(self):
        # override default --help option
        opt = self.parser.get_option("--help")
        opt.action = "store_true"
        opt.dest = "help"

    def run(self, *args, **kwargs):
        self.parser.print_help(admin=True)


class Help_RST(Command):
    """print program usage as reStructuredText"""
    enabled = True

    def options(self):
        pass

    def run(self, *args, **kwargs):
        prog = self.parser.get_prog_name()
        print ".. -*- coding: utf-8 -*-"
        print
        print "=" * len(prog)
        print prog
        print "=" * len(prog)
        print

        # add subtitle (command description)
        description = getattr(self.parser.container, "_description", None)
        if description:
            print ":Subtitle: %s" % description
            print

        # add copyright
        copyright = getattr(self.parser.container, "_copyright", None)
        if copyright:
            print ":Copyright: %s" % copyright

        # add date
        print ":Date: $Date: %s $" % datetime.datetime.strftime(datetime.datetime.utcnow(), format="%F %X")
        print

        print "--------"
        print "COMMANDS"
        print "--------"

        for command_name, CommandClass in sorted(self.parser.container.plugins.items()):
            parser = optparse.OptionParser(usage=self.parser.usage)
            cmd = CommandClass(parser)
            cmd.normalized_name = command_name
            cmd.options()
            cmd.container = self.parser.container
            cmd_opts, cmd_args = parser.parse_args()

            print command_name
            print "-" * len(command_name)

            if cmd.admin:
                print "[ADMIN ONLY]",

            print cmd.__doc__.strip()
            print
            usage = parser.get_usage().strip().replace("Usage: ", "**Usage:** ", 1)
            if usage:
                print usage
                print 

            for opt in sorted(parser.option_list, lambda x, y: cmp(str(x), str(y))):
                if "-h/--help" in str(opt):
                    continue
                if opt.nargs:
                    metavar = opt.metavar or opt.dest.upper()
                opt_list = []
                for opt_str in opt._short_opts + opt._long_opts:
                    if opt.nargs is not None:
                        opt_list.append("%s=%s" % (opt_str, metavar))
                    else:
                        opt_list.append(opt_str)
                print "/".join(opt_list)
                print "  %s" % opt.help
                if opt.action == "append":
                    print
                    print "  This option can be specified multiple times"
                print
            print

        # handle :Contact: and :Author: ourselves
        authors = force_list(getattr(self.parser.container, "_authors", []))
        contact = getattr(self.parser.container, "_contact", None)
        if authors or contact:
            print "-------"
            print "AUTHORS"
            print "-------"

            for author in sorted(authors):
                print "- %s" % author
            print

            if contact:
                print "**Contact:** %s" % contact
                print


CommandContainer.register_plugin(Help)
CommandContainer.register_plugin(Help_Admin)
CommandContainer.register_plugin(Help_RST)
