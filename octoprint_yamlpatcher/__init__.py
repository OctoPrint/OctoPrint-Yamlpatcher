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

	def _patch(self, unpatched, patch):
		import copy
		result = copy.deepcopy(unpatched)

		from functools import partial
		actions = ("move", "set", "merge", "append", "remove")
		funcs = {action: partial(getattr(self.__class__, "_patch_{}".format(action)), result)
		         for action in actions
		         if hasattr(self.__class__, "_patch_{}".format(action))}

		normalized = self.__class__._patch_normalize(patch, actions)
		for action, path, arg in normalized:
			funcs[action](path, arg)

		return result

	def _save_settings(self, patched):
		try:
			with open(self._settings._configfile, "wb") as f:
				self._to_yaml(patched, f)
			self._settings.load()
			self._event_bus.fire(octoprint.events.Events.SETTINGS_UPDATED)
		except:
			self._logger.exception("Error while writing patched settings to {}".format(self._settings._configfile))

	def _to_yaml(self, data, stream=None):
		import yaml
		return yaml.safe_dump(data,
		                      stream=stream,
		                      default_flow_style=False,
		                      indent="    ",
		                      allow_unicode=True)

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
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
