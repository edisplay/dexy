from dexy.filters.api import ApiFilter
import requests
#import inflection
import json
from dexy.exceptions import UserFeedback

class DrupalApiException(UserFeedback):
    pass

class DrupalFilter(ApiFilter):
    """
    Filter to post content to the Drupal8+ RESTful Web Services API.

    https://www.drupal.org/docs/8/core/modules/rest
    https://www.drupal.org/project/restui


    Uses Simple OAuth to authenticate.

    Simple OAuth:
    https://www.drupal.org/project/simple_oauth

    Video tutorials:
    https://youtube.com/playlist?list=PLZOQ_ZMpYrZtqy5-o7KoDhM3n6M0duBjX


    Params to be stored in a .dexyapis file, under the key "drupal".

    For the user you wish to post as:
        - username 
        - password

    For the site you wish to post to:
        - site (base URL starting with https)
        - client_id (UUID from the Consumer you wish to use)
        - client_secret (Client Secret from the Consumer you wish to use)

    Call the filter command fetch_tokens to retrieve an initial access token
    and refresh token.

    e.g. dexy fcmd -alias drupal -cmd fetch_tokens

    Tokens will be refreshed each time the filter is run,
    this may not be frequently enough to ensure tokens stay fresh.

    You can call the refresh_token filter command to refresh, or another call
    to fetch_tokens if tokens expire fully.


    ## Syntax Highlighting

    Recommended approach:

    Use the Pygments filter to apply css classes to highlighted code, and use
    something like Asset Injector to serve styles generated from the pygmentize
    command. This approach does the parsing when the page content is first
    generated and not when it is displayed.

    https://www.drupal.org/project/asset_injector

    You could also use something like PrismJS which does the parseing
    client-side. It would not be hard to write a dexy filter which applied
    language tags.
    https://prismjs.com/

    """
    aliases = ['drupal', 'd8']
    _settings = {
            'verify-ssl' : False,
            'api-key-name' : 'drupal',
            'document-config-required' : False,
            'document-api-config-postfix' : "-config.json",
            'input-extensions' : ['.html'],
            'output-extensions' : ['.txt'],
            'format' : 'full_html'
            }

    def gen_headers(self, include_json=True):
        headers = {"Authorization" : "Bearer %s" % self.read_param('access_token')}
        if include_json:
            headers["Content-type"] = "application/json"
        return headers

    def oauth_post_request(self, params):
        url = self.read_param("site") + "/oauth/token/"
        r = requests.post(url, data=params, verify=self.setting('verify-ssl'))
        token_info = r.json()
        self.write_params(token_info)

    def docmd_refresh_token(self):
        """
        Run with e.g. dexy fcmd -alias drupal -cmd refresh_token
        """
        params = {
                "grant_type" : "refresh_token",
                "refresh_token" : self.read_param("refresh_token"),
                "client_id" : self.read_param("client_id"),
                "client_secret" : self.read_param("client_secret"),
                }
        self.oauth_post_request(params)

    def docmd_fetch_tokens(self):
        """
        Run with e.g. dexy fcmd -alias drupal -cmd fetch_token
        """
        params = {
                "grant_type" : "password",
                "client_id" : self.read_param("client_id"),
                "client_secret" : self.read_param("client_secret"),
                "username" : self.read_param("username"),
                "password" : self.read_param("password"),
                }
        self.oauth_post_request(params)

    def api_request(self, verb, url, json=None):
        if verb == 'get':
            return requests.get(url, params={"_format" : "json"}, headers=self.gen_headers(), verify=self.setting('verify-ssl'))
        elif verb == 'post':
            return requests.post(url, params={"_format" : "json"}, headers=self.gen_headers(), verify=self.setting('verify-ssl'),
                    json=json)
        elif verb == 'patch':
            return requests.patch(url, params={"_format" : "json"}, headers=self.gen_headers(), verify=self.setting('verify-ssl'),
                    json=json)
        else:
            raise Exception("unknown rest verb '%s'" % verb)

    def docmd_read_node(self, node):
        self.docmd_refresh_token()
        url = self.read_param("site") + "/node/%s" % node
        r = self.api_request('get', url)
        print(json.dumps(r.json(), sort_keys=True, indent=4))

    def process_text(self, text):
        # refresh token each time - may not be enough
        self.docmd_refresh_token()

        document_config = self.read_document_config()

        title = document_config.get('title') or self.doc.runtime_args.get('title')
        #slug = document_config.get('slug', inflection.parameterize(title))
        node_id = document_config.get('node_id')

        content = {
                "body" : [{
                    "format" : "full_html",
                    "value" : text
                    }],
                "title" : {
                    "value" : title
                    },
                "type" : [{
                    "target_id" : self.doc.runtime_args.get('type')
                    }]
                }

        url = self.read_param("site") + "/node"
        if node_id:
            # update an existing node
            url += "/%s" % node_id
            r = self.api_request('patch', url, json=content)
        else:
            # create a new node
            r = self.api_request('post', url, json=content)

        node_info = r.json()

        if 'message' in node_info:
            raise DrupalApiException(node_info['message'])

        document_config['node_id'] = node_info['nid'][0]['value']
        self.save_document_config(document_config)

        return json.dumps(node_info, indent=4, sort_keys=True)
