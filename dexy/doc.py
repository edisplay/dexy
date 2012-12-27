import dexy.artifact
import dexy.exceptions
import dexy.filter
import dexy.task
import os
import posixpath

class Doc(dexy.task.Task):
    """
    Task subclass representing Documents.
    """
    ALIASES = ['document']

    def arg_value(self, arg_name_hyphen, default=None):
        return dexy.utils.value_for_hyphenated_or_underscored_arg(self.args, arg_name_hyphen, default)

    def filter_class_for_alias(self, alias):
        if alias == '':
            blank_alias_msg = "You have a trailing | or you have 2 | symbols together in your specification for %s"
            raise dexy.exceptions.UserFeedback(blank_alias_msg % self.key)
        elif alias.startswith("-"):
            filter_class = dexy.filter.AliasFilter
        else:
            try:
                filter_class = dexy.filter.Filter.aliases[alias]
            except KeyError:
                msg = "Dexy doesn't have a filter '%s' available." % alias

                all_plugins = dexy.filter.Filter.aliases.values()
                num_plugins = len(all_plugins)
                if num_plugins < 10:
                    plugin_list = ", ".join(p.__name__ for p in all_plugins)
                    msg += " Note that only %s plugins are available: %s" % (num_plugins, plugin_list)
                    msg += " There may be a problem loading plugins, adding 'import dexy.plugins' might help."

                raise dexy.exceptions.UserFeedback(msg)

        if not filter_class.is_active():
            raise dexy.exceptions.InactiveFilter(alias, self.key)

        return filter_class

    def names_to_docs(self):
        """
        Returns a dict whose keys are canonical names, whose values are lists
        of the docs that generate that name as their canonical output name.
        """
        names_to_docs = {}
        for doc in self.node.walk_input_docs():
            doc_name = doc.output().name
            if names_to_docs.has_key(doc_name):
                names_to_docs[doc_name].append(doc)
            else:
                names_to_docs[doc_name] = [doc]
        return names_to_docs

    def conflicts(self):
        """
        List of inputs to document where more than 1 doc generates same
        canonical filename.
        """
        conflicts = {}
        for k, v in self.names_to_docs().iteritems():
            if len(v) > 1:
                conflicts[k] = v
        return conflicts

    def is_index_page(self):
        fn = self.output().name
        # TODO index.json only if htmlsections in doc key..
        return fn.endswith("index.html") or fn.endswith("index.json")

    def title(self):
        if self.args.get('title'):
            return self.args.get('title')
        elif self.is_index_page():
            # use subdirectory we're in
            return posixpath.split(posixpath.dirname(self.name))[-1].capitalize()
        else:
            return self.name

    def output(self):
        """
        Returns a reference to the output_data Data object generated by the final filter.
        """
        final_state = self.final_artifact.state
        if not final_state == 'complete':
            if not final_state == 'setup' and len(self.filters) == 0:
                raise dexy.exceptions.InternalDexyProblem("Final artifact state is '%s'" % self.final_artifact.state)

        return self.final_artifact.output_data

    def add_artifact(self, artifact):
        self.children.append(artifact)
        self.final_artifact = artifact

    def setup_initial_artifact(self):
        if os.path.exists(self.name):
            initial = dexy.artifact.InitialArtifact(self.name, wrapper=self.wrapper)
        else:
            initial = dexy.artifact.InitialVirtualArtifact(self.name, wrapper=self.wrapper)

        initial.args = self.args
        initial.name = self.name
        initial.prior = None
        initial.doc = self
        initial.created_by_doc = self.created_by_doc
        initial.remaining_doc_filters = self.filters

        initial.transition('populated')
        self.add_artifact(initial)

    def setup_filter_artifact(self, key, filters):
        filter_alias = filters[-1]

        remaining_filters = self.filters[len(filters):len(self.filters)]
        is_last_filter = len(remaining_filters) == 0

        artifact = dexy.artifact.FilterArtifact(key, wrapper=self.wrapper)

        artifact.remaining_doc_filters = remaining_filters
        artifact.set_log()
        artifact.log.addHandler(self.log.handlers[0])

        # skip args that are only relevant to the doc or to the initial artifact
        skip_args = ['contents', 'contentshash', 'data-class-alias', 'depends']
        artifact.args = dict((k, v) for k, v in self.args.iteritems() if not k in skip_args)

        artifact.doc = self
        artifact.prior = self.children[-1]
        artifact.created_by_doc = self.created_by_doc

        artifact.filter_alias = filter_alias
        artifact.filter_class = self.filter_class_for_alias(filter_alias)
        artifact.setup_filter_instance()

        if not is_last_filter:
            next_filter_alias = self.filters[len(filters)]
            artifact.next_filter_alias = next_filter_alias
            artifact.next_filter_class = self.filter_class_for_alias(next_filter_alias)
            artifact.next_filter_name = artifact.next_filter_class.__name__
        else:
            artifact.next_filter_alias = None
            artifact.next_filter_class = None
            artifact.next_filter_name = None

        artifact.transition('populated')
        self.add_artifact(artifact)

    def setup(self):
        self.hashstring = self.final_artifact.hashstring

    def populate(self):
        self.set_log()
        self.name = self.key.split("|")[0]
        self.filters = self.key.split("|")[1:]
        self.canon = self.args.get('canon', len(self.filters) == 0)

        self.setup_initial_artifact()

        for i in range(0,len(self.filters)):
            filters = self.filters[0:i+1]
            key = "%s|%s" % (self.name, "|".join(filters))
            self.setup_filter_artifact(key, filters)
            self.canon = self.canon or (not self.final_artifact.filter_class.FRAGMENT)

