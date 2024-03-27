# Python Wiki API

## Setup

### Local/Docker

With Docker running, run:

```shell
docker-compose up
```

Access the container in a browser at `http://localhost:8080`

Go through the Wiki set up.

When it asks for database information, enter the following:

- Database host: database:3306
- Database username: root
- Database password: root (or the value specified in `docker-compose.yml:services.database.environment.MYSQL_ROOT_PASSWORD`)

On the `Name` page, create an account.

Go through the rest of the setup (`TODO might need to go over some settings here... we should also be able to change things in LocalSettings.php`)

Want to allow image uploads - this can be updated later by setting `$wgEnableUploads` to `true`

When it asks, download `LocalSettings.php`. Place this file in the same place as the `docker-compose.yml` file.

Stop the docker containers (this can done by running `docker-compose down` in the same files as `docker-compose.yml`). Uncomment the line containing `- ./LocalSettings.php:/var/www/html/LocalSettings.php` in the `docker-compse.yml`. Stand the containers back up again by running `docker-compose up`. The wiki should now be available at `http://localhost:8080`.

Once the wiki is up, you can log in using the user credentials created during the wiki setup.

#### API Access

The API is available at: `localhost:8080/api.php`

There may be a way to configure the path (other wiki APIS seem to be available at `.../w/api.php` or `.../wiki/api.php`). Most documentation online uses URLs with those paths, but by default, it seems to just be `.../api.php`

#### Uploading Files

Once you log in, you can go to your account (`localhost:8080/index.php/User:<username>`) and select `Upload File` on the right panel. Once the file has been uploaded, you can reference it in wiki pages like: `[[File:<filename>]]`

#### Bot Password

A bot password can be used to programmatically modify the wiki - create/delete/update pages, upload images, etc. 

Create a bot password at the following link: http://localhost:8080/index.php/Special:BotPasswords

Provide a bot name and select necessary permissions. Once you create the bot password, you can use the credentials for this script.

> [!NOTE]
> We may want to use a bot to "seed" the wiki with data; images, templates, css, etc.

#### Enabling Extensions

If you want to create your own templates, like infoboxes, you must download and load the [ParserFunctions Extension](https://www.mediawiki.org/wiki/Extension:ParserFunctions). Inside the docker container, the extension has already been downloaded, so all that is needed is to add `wfLoadExtension( 'ParserFunctions' );` at the bottom of `LocalSettings.php`. 

#### Creating an Infobox

[Source](https://stackoverflow.com/questions/27801082/how-do-you-make-infoboxes-in-mediawiki)

> [!WARNING]
> ParserFunctions extension must be enabled to do this.

1. Navigate to the page with the name of the infobox you want to create. For instance, if you wanted to create a `unit` infobox, go to: http://localhost:8080/index.php/Template:Infobox_mapobject
2. Select `Edit`. Add in HTML for the infobox. A boilerplate one:

```html
<div class="infobox">
    <div class="infobox-title">{{{title|{{PAGENAME}}}}}</div>
{{#if:{{{card-image|}}}|<div class="infobox-image">[[File:{{PAGENAME:{{{card-image}}}}}|150px]]</div>}}
    <table class="infobox-table">
{{#if:{{{cost|}}}|<tr>
            <th>Cost</th>
            <td>{{{cost}}}</td>
        </tr>}}{{#if:{{{attack|}}}|<tr>
            <th>Attack</th>
            <td>{{{attack}}}</td>
        </tr>}}{{#if:{{{defense|}}}|<tr>
            <th>Defense</th>
            <td>{{{defense}}}</td>
        </tr>}}{{#if:{{{movement|}}}|<tr>
            <th>Movement</th>
            <td>{{{movement}}}</td>
        </tr>}}{{#if:{{{countdown|}}}|<tr>
            <th>Countdown</th>
            <td>{{{countdown}}}</td>
        </tr>}}{{#if:{{{effect|}}}|<tr>
            <th>Effect</th>
            <td>{{{effect}}}</td>
        </tr>}}{{#if:{{{traits|}}}|<tr>
            <th>Traits</th>
            <td>{{{traits}}}</td>
        </tr>}}
    </table>
{{#if:{{{map-image|}}}|<div class="infobox-image">[[File:{{PAGENAME:{{{map-image}}}}}|100px]]</div>}}
</div>

```

3. To add styling, log in and go to: http://localhost:8080/index.php/MediaWiki:Common.css 
4. Edit to add in your styling. Some styling for the above boilerplate might be something like:

```css
.infobox {
    background: #eee;
    border: 1px solid #aaa;
    float: right;
    margin: 0 0 1em 1em;
    padding: 0.75em;
    width: 300px;
}
.infobox-title {
    font-size: 2em;
    text-align: center;
}
.infobox-image {
    text-align: center;
}
.infobox-table th {
    text-align: right;
    vertical-align: top;
    width: 100px;
}
.infobox-table td {
    vertical-align: top;
}
```

5. Go to the page you want to add the infobox. Edit the page, and paste in the following, updating values as necessary:

```text
{{Infobox unit
| title = My unit
| image = 
| param1 = 1
| param2 = 2
| param3 = 3
| param4 = 4
| param5 = 5
}}
```

## Release

- Create a new tag:

```sh
git tag v<tag-name> main
```

- Push:

> [!WARNING]
> For some reason, one of the releases failed. Rerunning the job fixed it.

```sh
git push origin v<tag-name>
```



## Commands to Download Release

First, need asset ID of the release. Send a request to:

```sh
set TAG=v0.1.0
curl -L "https://api.github.com/repos/jTendeck/mediawiki-uploader/releases/tags/%TAG%"
```
45[]
Find the asset ID for the tag to download. This can be found in `[n].assets[n].id`... or use the assets URL.

Then download using:

```sh
set ASSET_ID=
set OUTPUT_FILE=WikiUploader.zip

curl -H "Accept: application/octet-stream" -L https://api.github.com/repos/jTendeck/mediawiki-uploader/releases/assets/%ASSET_ID% -o %OUTPUT_FILE%
```
