# coding=utf-8
from __future__ import absolute_import

__author__ = "Gina Häußge <osd@foosel.net>"
__license__ = 'GNU Affero General Public License http://www.gnu.org/licenses/agpl.html'
__copyright__ = "Copyright (C) 2015 The OctoPrint Project - Released under terms of the AGPLv3 License"

import octoprint.plugin
import octoprint.events

from octoprint.server import admin_permission

class YamlpatcherPlugin(octoprint.plugin.TemplatePlugin,
                        octoprint.plugin.SettingsPlugin,
                        octoprint.plugin.SimpleApiPlugin,
                        octoprint.plugin.AssetPlugin):

	##~~ Softwareupdate hook

	def get_update_information(self):
		return dict(
			yamlpatcher=dict(
				displayName="Yamlpatcher Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="OctoPrint",
				repo="OctoPrint-Yamlpatcher",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/OctoPrint/OctoPrint-Yamlpatcher/archive/{target_version}.zip"
			)
		)

	##~~ CLI hook

	def get_cli_commands(self, cli, pass_octoprint_ctx, *args, **kwargs):

		settings = cli._settings
		plugin_settings = octoprint.plugin.plugin_settings_for_settings_plugin("yamlpatcher", self, settings=settings)
		if plugin_settings is None:
			return []

		self._settings = plugin_settings
		self._plugin_manager = cli._plugin_manager

		import click
		import json
		import sys

		class PatchContext(object):
			def __init__(self, target="settings", apply=False):
				self.target = target
				self.apply = apply
		pass_patch_ctx = click.make_pass_decorator(PatchContext, ensure=True)

		conversions = dict(
			str=str,
			int=int,
			float=float,
			bool=lambda x: x and x.lower() in ("true", "yes", "y", "1", "on"),
			json=lambda x: json.loads(x)
		)

		def convert_value(value, data_type):
			"""Convert the value into the provided data type."""
			if not data_type in conversions:
				raise KeyError()
			return conversions[data_type](value)

		def create_patch(operation, path, value, data_type="str"):
			"""Create a patch data structure for the given operation, path and value."""
			try:
				value = convert_value(value, data_type)
			except IndexError:
				click.echo("Invalid data type: {}".format(data_type))
				sys.exit(-1)
			except ValueError:
				click.echo("Invalid {}: {!r}".format(data_type, value))
				sys.exit(-1)

			return [operation, path, value]

		def operation(patch_ctx, operation, path, value, data_type):
			"""Perform the specified operation for the given path, value and context."""
			import difflib

			# figure out our context
			apply = patch_ctx.apply
			confirmed = patch_ctx.confirmed
			unpatched = patch_ctx.unpatched
			if unpatched is None:
				click.echo("Unknown target: {}".format(patch_ctx.target))

			# create the patch
			patch = create_patch(operation, path, value, data_type=data_type)

			# apply the patch
			patched = self.__class__._patch(unpatched, [patch])

			# create diff of the unpatched and patched document
			unpatched_yaml = self.__class__._to_yaml(unpatched)
			patched_yaml = self.__class__._to_yaml(patched)
			diff = difflib.unified_diff(unpatched_yaml.split("\n"), patched_yaml.split("\n"), fromfile=patch_ctx.filename + ".old", tofile=patch_ctx.filename)

			# print the diff ...
			changes = False
			for line in diff:
				click.echo(line)
				changes = True

			# ... or inform that there is no diff
			if not changes:
				click.echo("No changes!")
				sys.exit(0)

			# if we also were asked to apply the patch, make sure the user is absolutely positiv
			if apply:
				if not confirmed and not click.confirm("Are you sure you want to apply the above changes?"):
					click.echo("Changes not applied!")
					sys.exit(0)

				if patch_ctx.target == "settings":
					# patch config.yaml
					self._save_settings(patched)
					click.echo("config.yaml patched, please restart OctoPrint for the changes to take effect")


		@click.group("patch")
		@click.option("--target", type=click.Choice(["settings"]), default="settings",
		              help="The target to apply the patch to. Currently only \"settings\" (config.yaml) is supported.")
		@click.option("--apply", is_flag=True,
		              help="Whether to also apply the patch. If not set, only a diff will be printed.")
		@click.option("--yes", "-y", "confirmed", is_flag=True,
		              help="Overrides the interactive confirmation prompt on patch apply.")
		@pass_patch_ctx
		def patch(patch_ctx, target, apply, confirmed):
			"""Patch a yaml file."""
			patch_ctx.target = target
			patch_ctx.apply = apply
			patch_ctx.confirmed = confirmed

			patch_ctx.unpatched = None
			patch_ctx.filename = None
			if target == "settings":
				self._settings.load()
				patch_ctx.unpatched = self._settings._config
				patch_ctx.filename = "config.yaml"

		@patch.command("set")
		@click.argument("path", type=click.STRING)
		@click.argument("value", type=click.STRING)
		@click.option("--type", "data_type", type=click.Choice(["str", "int", "float", "bool", "json"]), default="str")
		@pass_patch_ctx
		def set(patch_ctx, path, value, data_type):
			"""Set the given path to the given value."""
			operation(patch_ctx, "set", path, value, data_type)

		@patch.command("merge")
		@click.argument("path", type=click.STRING)
		@click.argument("value", type=click.STRING)
		@pass_patch_ctx
		def merge(patch_ctx, path, value):
			"""Merge the given value onto the value at the given path."""
			operation(patch_ctx, "merge", path, value, "json")

		@patch.command("move")
		@click.argument("source", type=click.STRING)
		@click.argument("target", type=click.STRING)
		@pass_patch_ctx
		def move(patch_ctx, source, target):
			"""Move the value from source to target."""
			operation(patch_ctx, "move", source, target, "str")

		@patch.command("remove")
		@click.argument("path", type=click.STRING)
		@pass_patch_ctx
		def remove(patch_ctx, path):
			"""Remove the value at the given path."""
			operation(patch_ctx, "remove", path, "", "str")

		@patch.command("append")
		@click.argument("path", type=click.STRING)
		@click.argument("value", type=click.STRING)
		@click.option("--type", "data_type", type=click.Choice(["str", "int", "float", "bool", "json"]), default="str")
		@pass_patch_ctx
		def append(patch_ctx, path, value, data_type):
			"""Append the value to the list at the given path."""
			operation(patch_ctx, "append", path, value, data_type)

		return [patch]

	##~~ AssetPlugin

	def get_assets(self):
		return dict(
			css=["css/yamlpatcher.css"],
			js=["js/jsdiff.js", "js/js-yaml.min.js", "js/yamlpatcher.js"],
			less=["less/yamlpatcher.less"]
		)

	##~~ SimpleApiPlugin

	def get_api_commands(self):
		return dict(
			preview=["target", "patch"],
			apply=["target", "patch"]
		)

	def on_api_command(self, command, data):
		import flask

		if not admin_permission.can():
			return flask.make_response("Insufficient rights", 403)

		target = data["target"]
		patch = data["patch"]

		if target not in ("settings",):
			return flask.make_response("Unknown target: {}".format(target), 400)

		if target == "settings":
			self._settings.load()
			unpatched = self._settings._config

		patched = self._patch(unpatched, patch)

		if command == "apply":
			if target == "settings":
				self._save_settings(patched)

		return flask.jsonify(old=self._to_yaml(unpatched), new=self._to_yaml(patched))

	##~~ Helpers

	def _save_settings(self, patched):
		try:
			with open(self._settings._configfile, "wb") as f:
				self._to_yaml(patched, f)
			self._settings.load()
			self._event_bus.fire(octoprint.events.Events.SETTINGS_UPDATED)
		except:
			self._logger.exception("Error while writing patched settings to {}".format(self._settings._configfile))

	@classmethod
	def _to_yaml(cls, data, stream=None):
		import yaml
		return yaml.safe_dump(data,
		                      stream=stream,
		                      default_flow_style=False,
		                      indent="    ",
		                      allow_unicode=True)

	@classmethod
	def _patch(cls, unpatched, patch):
		import copy
		result = copy.deepcopy(unpatched)

		from functools import partial
		actions = ("move", "set", "merge", "append", "remove")
		funcs = {action: partial(getattr(cls, "_patch_{}".format(action)), result)
		         for action in actions
		         if hasattr(cls, "_patch_{}".format(action))}

		normalized = cls._patch_normalize(patch, actions)
		for action, path, arg in normalized:
			funcs[action](path, arg)

		return result

	@classmethod
	def _patch_normalize(cls, patch, actions):
		"""
		Normalizes and validates a patch.

		It is ensured that:

		  * the patch is a list consisting of
		  * only lists with exactly three items of which
		  * the first entry will be a valid action,
		  * the second entry will be a list specifying a path to a node,
		  * the third entry will be a list specifying a path to a node for
		    move actions, otherwise it will be left alone
		"""

		if not isinstance(patch, list) or not patch:
			return []

		patch = [item for item in patch if isinstance(item, list) and
		         len(item) == 3]

		def to_path(node):
			if isinstance(node, basestring):
				if node.strip() == "":
					return []
				return node.split(".")
			elif isinstance(node, (list, tuple)):
				return list(node)
			else:
				raise ValueError("node must be either string, list or tuple")

		def convert_paths(action, path, arg):
			path = to_path(path)
			if action == "move":
				arg = to_path(arg)
			return [action, path, arg]

		def normalize_entry(action, path, arg):
			if path:
				return [convert_paths(action, path, arg)]
			elif isinstance(arg, dict):
				return [convert_paths(action, [key], arg[key]) for key in arg]
			else:
				return None

		result = []
		for item in patch:
			action, node, arg = item
			if action not in actions:
				continue
			entry = normalize_entry(action, node, arg)
			if entry is None:
				continue
			result += entry

		return result

	@classmethod
	def _patch_get_parent(cls, root, path, add=False):
		"""
		Finds the parent data structure for the provided path.

		If ``add`` is true and the full path doesn't yet exist, new
		dict nodes will be added to the structure.
		"""
		if not path:
			return root

		value = root
		if len(path) > 1:
			for p in path[:-1]:
				if p in value:
					value = value[p]
				elif add:
					value[p] = dict()
					value = value[p]
				else:
					return None

		if path[-1] in value:
			return value
		elif add:
			value[path[-1]] = dict()
			return value
		else:
			return None

	@classmethod
	def _patch_move(cls, root, path_from, path_to):
		"""
		Moves the value at the node specified by ``path_from`` to
		the node at ``path_to``.
		"""
		if not path_from or not path_to:
			return

		parent_from = cls._patch_get_parent(root, path_from)
		if parent_from is None:
			return

		parent_to = cls._patch_get_parent(root, path_to, add=True)

		from_key = path_from[-1]
		to_key = path_to[-1]

		parent_to[to_key] = parent_from[from_key]
		del parent_from[from_key]

	@classmethod
	def _patch_set(cls, root, path, value, merge=False):
		"""
		Sets the node specified by path to the provided value, optionally
		merging with existing data.

		If ``merge`` is true, will try to merge dictionaries and lists:
		If the node and the value are dictionaries, merges the existing
		data with the provided value. If the node is a list, appends all
		items from ``value`` (if value is a list), or just the value to
		the existing data. Otherwise no action will be taken when ``merge``
		is true.

		If ``merge`` is not true (default), will just set the provided
		value as the new value for the node specified by the path.
		"""
		if not path:
			return

		parent = cls._patch_get_parent(root, path, add=True)
		if parent is None:
			return
		if not isinstance(parent, dict):
			return

		def merged_value(existing, new):
			if isinstance(existing, dict) and isinstance(new, dict):
				from octoprint.util import dict_merge
				return dict_merge(existing, new)
			elif isinstance(existing, list):
				if not isinstance(new, list):
					new = [new]

				data = existing
				for v in new:
					data.append(v)
				return data
			else:
				return None

		key = path[-1]

		if merge and key in parent:
			value = merged_value(parent[key], value)
			if value is None:
				return

		parent[key] = value

	@classmethod
	def _patch_merge(cls, root, path, value):
		"""
		Merges the node specified by path with the provided value.
		"""
		cls._patch_set(root, path, value, merge=True)

	@classmethod
	def _patch_append(cls, root, path, value):
		"""
		Appends the provided value to the list element at path.

		Does nothing if path doesn't specify a list element.
		"""

		parent = cls._patch_get_parent(root, path)
		if parent is None:
			return

		if path:
			key = path[-1]
			if isinstance(parent, dict):
				if not key in parent:
					parent[key] = list()
				if isinstance(parent[key], list):
					parent[key].append(value)
		elif isinstance(parent, list):
			parent.append(value)

	@classmethod
	def _patch_remove(cls, root, path, value):
		"""
		Removes the node specified by path from the structure.

		If the node is a list and value is set, it will remove the value
		from the list, otherwise the whole node will be removed.

		Does nothing if path is neither a dictionary nor a list.
		"""

		if not path:
			return

		parent = cls._patch_get_parent(root, path)
		if parent is None:
			return

		key = path[-1]
		if value and key in parent and isinstance(parent[key], list):
			parent[key].remove(value)
		elif isinstance(parent, dict):
			if key in parent:
				del parent[key]

__plugin_name__ = "Yamlpatcher"
def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = YamlpatcherPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
		"octoprint.cli.commands": __plugin_implementation__.get_cli_commands
	}
