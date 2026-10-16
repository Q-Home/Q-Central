# Microsoft Entra ID voor Q-Central

Deze handleiding beschrijft de geïmplementeerde login, de inrichting in Entra en
het beheer op de server. De standaardaanpak sluit aan op de **beheerdersrol van
Cohvera**: `SG-PORTAL-Admins → Portal.Admin → Q-Central admin`.

Een succesvolle aanmelding in de Entra-logs bewijst de Microsoft-authenticatie.
Q-Central controleert daarna zelf of de gebruiker toegang krijgt. Zonder passende
rol of expliciet ingestelde groep wordt geen applicatiesessie aangemaakt.

## Inhoud

- [1. Welke gegevens zijn nodig?](#1-welke-gegevens-zijn-nodig)
- [2. Entra instellen zoals bij Cohvera](#2-entra-instellen-zoals-bij-cohvera)
- [3. De server configureren](#3-de-server-configureren)
- [4. Deployen en controleren](#4-deployen-en-controleren)
- [5. Problemen oplossen](#5-problemen-oplossen)
- [6. Optioneel: directe controle op groeps-ID](#6-optioneel-directe-controle-op-groeps-id)
- [7. Werking, sessies en beheer](#7-werking-sessies-en-beheer)
- [8. Ontwikkeling en tests](#8-ontwikkeling-en-tests)

## 1. Welke gegevens zijn nodig?

| Gegeven | Waar te vinden | Gebruik |
| --- | --- | --- |
| Directory (tenant) ID | Entra → App registrations → Q-Central → Overview | Dezelfde organisatietenant als Cohvera |
| Application (client) ID | Dezelfde Overview-pagina | Eigen ID van de Q-Central-appregistratie |
| Client secret **Value** | Q-Central → Certificates & secrets → Client secrets | Secret van **diezelfde** Q-Central-appregistratie |
| Secret ID / Geheim-id | Naast de secret-value | Niet invullen in Q-Central |
| Object ID van een groep | Entra → Groups → groep → Overview | Alleen nodig voor het optionele alternatief in sectie 6 |

Het vervangen van een secret verandert de client-ID en tenant-ID niet. Een nieuwe
appregistratie krijgt wel een nieuwe client-ID. Gebruik in Q-Central geen
client-ID/secret van de Cohvera-appregistratie.

## 2. Entra instellen zoals bij Cohvera

Deze stappen voert iemand met de nodige Entra-beheerrechten uit. De code kan geen
redirect-URI, app-rollen, groepslidmaatschappen of roltoewijzingen in Entra aanmaken.

### Appregistratie en redirect-URI

1. Open **App registrations → Q-Central** in de tenant van jullie organisatie.
2. Controleer dat **Application (client) ID** overeenkomt met de client-ID die op
   de server gebruikt wordt. Kies een single-tenant registratie.
3. Open **Authentication → Add a platform → Web** en registreer exact:

   ```text
   https://central.q-home.be/api/auth/entra/callback
   ```

4. Sla op. Gebruik voor een ander domein dezelfde callbackroute onder dat domein.
   Implicit grant en public-client flows zijn niet nodig voor deze implementatie.
5. Maak onder **Certificates & secrets** een client secret en bewaar de **Value**
   voor de serverconfiguratie. Noteer de vervaldatum en verantwoordelijke beheerder.

De redirect-URI is optioneel bij het aanmaken van een generieke Entra-app, maar
vereist voor deze interactieve web-login. Een `.env`-regel registreert de URL niet
bij Microsoft. Gebruik het platform **Web**; de tokenuitwisseling gebeurt bij de API.
Zie [Microsoft: redirect-URI's](https://learn.microsoft.com/en-us/entra/identity-platform/reply-url).

### De bestaande beheerdersgroep toewijzen

1. Open **App registrations → Q-Central → App roles → Create app role**.
2. Gebruik bijvoorbeeld deze instellingen:

   | Veld | Waarde |
   | --- | --- |
   | Display name | Portal Admin |
   | Allowed member types | Users/Groups |
   | Value | `Portal.Admin` |
   | Description | Beheertoegang tot Q-Central |
   | Enabled | Ja |

3. Open **Enterprise applications → Q-Central → Users and groups → Add user/group**.
4. Selecteer de bestaande groep **SG-PORTAL-Admins** en de rol **Portal Admin**.
5. Controleer dat de beoogde gebruiker rechtstreeks lid is van die groep.
6. Zet bij **Properties → Assignment required?** de waarde op **Yes**.
7. Laat Entra MFA en Conditional Access toepassen volgens jullie organisatiebeleid.

De groep mag dezelfde zijn als bij Cohvera. De **toewijzing aan de Q-Central-app**
moet wel apart bestaan. Lidmaatschap van de groep, een Cohvera-toewijzing of
**Default Access** alleen levert niet automatisch de `Portal.Admin`-claim voor
Q-Central. Voor deze aanpak zijn geen groeps-ID's in `.env` en geen `groups`-claim
nodig. Groepstoewijzing vereist een passende Entra-licentie; als die ontbreekt kan
een beheerder de app-rol rechtstreeks aan een gebruiker toewijzen.
Zie [Microsoft: rollen definiëren](https://learn.microsoft.com/entra/identity-platform/howto-add-app-roles-in-apps)
en [gebruikers en groepen toewijzen](https://learn.microsoft.com/en-us/entra/identity/enterprise-apps/assign-user-or-group-access-portal).

### Rollen die Q-Central accepteert

| Exacte waarde in de `roles`-claim | Lokale rol | Toegang |
| --- | --- | --- |
| `Portal.Admin` | `admin` | Beheer; dezelfde beheerdersrolnaam als Cohvera |
| `QCentral.Admin` | `admin` | Bestaande Q-Central-rol blijft werken |
| `QCentral.SuperAdmin` | `superadmin` | Superadmin |
| `Portal.User` | Geen | Geen toegang tot dit beheerplatform |
| `SG-PORTAL-Admins` als rolnaam | Geen | Groepsnaam is geen app-rol |
| Geen passende rol | Geen | Geweigerd, tenzij een expliciete groeps-ID-koppeling past |

Waarden zijn hoofdlettergevoelig: `portal.admin` is niet `Portal.Admin`.
Q-Central heeft geen volledige fijnmazige API-autorisatie voor lezers, support en
installateurs; daarom worden gewone Cohvera-gebruikers niet automatisch toegelaten.
Admin en superadmin hebben beide brede beheertoegang; de twee labels bieden hier
geen garantie op een uitgebreide scheiding van alle functies.

## 3. De server configureren

Bij de productie-Compose-stack staat het bestand normaal op:

```text
/opt/Q-Central/deploy/.env
```

Zoek het zo nodig met `find /opt/Q-Central -type f -name '.env'`. Het bestand is
verborgen: gebruik `ls -la` om het te zien. `nano` kan ook een nieuw leeg bestand
openen; controleer het pad voordat je daarin configuratie opslaat.

Open het **bestaande** bestand en voeg onderstaande instellingen toe of pas de
bestaande regels aan. Behoud database-, ZeroTier-, portal- en overige instellingen.
Zet iedere variabele maar één keer in het bestand.

```bash
nano /opt/Q-Central/deploy/.env
```

```dotenv
Q_CENTRAL_AUTH_MODE=entra
Q_CENTRAL_HOSTNAME=central.q-home.be
Q_CENTRAL_EXTERNAL_URL=https://central.q-home.be
Q_CENTRAL_CORS_ORIGINS=https://central.q-home.be
Q_CENTRAL_ENTRA_TENANT_ID=<Directory tenant ID>
Q_CENTRAL_ENTRA_CLIENT_ID=<Application client ID van Q-Central>
Q_CENTRAL_ENTRA_CLIENT_SECRET=<Client secret VALUE van Q-Central>
Q_CENTRAL_ENTRA_SESSION_MINUTES=15
```

Vervang de placeholders; bovenstaande IDs en secret zijn geen werkende waarden.
`HOSTNAME` bepaalt de Caddy-hostnaam, `EXTERNAL_URL` de publieke URL en callback,
en `CORS_ORIGINS` de toegestane browserorigin. Houd die voor deze installatie
consistent. HTTPS is verplicht in Entra-modus, ook bij een lokale Entra-test.

`Q_CENTRAL_SECRET_KEY` blijft daarnaast vereist: dit is de bestaande eigen
Q-Central-sleutel van minstens 32 tekens voor het ondertekenen van sessies. Het is
**niet** de Entra client secret. Voor een nieuwe installatie kan een beheerder
hiervoor `openssl rand -hex 32` gebruiken. Wijzig deze sleutel bij een bestaande
installatie niet zonder reden: daarmee worden alle bestaande sessies ongeldig.

| Instelling | Gedrag |
| --- | --- |
| `Q_CENTRAL_AUTH_MODE` | Standaard `entra`; geen automatische terugval op lokaal |
| `Q_CENTRAL_ENTRA_SESSION_MINUTES` | Standaard 15; toegestaan 1–60 minuten |
| `Q_CENTRAL_ENTRA_ADMIN_GROUP_IDS` | Optioneel; leeg laten voor de Cohvera-app-rolaanpak |
| `Q_CENTRAL_ENTRA_SUPERADMIN_GROUP_IDS` | Optioneel; leeg laten voor de Cohvera-app-rolaanpak |
| `ENTRA_REDIRECT_URI` | Wordt niet gelezen; mag verwijderd worden |
| `Q_CENTRAL_ENTRA_REDIRECT_URI` | Bestaat niet als instelling; wordt niet gelezen |

De callback wordt automatisch berekend als `Q_CENTRAL_EXTERNAL_URL` zonder
laatste slash, gevolgd door `/api/auth/entra/callback`. `/auth/callback` is niet
de callbackroute van deze implementatie. Sla geen secrets op in Git, documentatie
of screenshots. Bij een gedeelde secret: maak een vervanger bij dezelfde
appregistratie, pas alleen de secret-value aan, hermaak de API, test de login en
verwijder het oude secret. Bij vermoed misbruik trek je het oude secret direct in.

## 4. Deployen en controleren

### Bij nieuwe code

Commit en push eerst de lokale wijzigingen. Een server-`git pull` haalt geen code
op die alleen op de ontwikkelcomputer staat. Voer daarna op de server uit:

```bash
cd /opt/Q-Central
git pull --ff-only
cd deploy
docker compose -f docker-compose.production.yml up -d --build api frontend
docker compose -f docker-compose.production.yml ps
```

De productie-stack vereist ook de bestaande databaseconfiguratie, waaronder
`POSTGRES_PASSWORD`. Een Entra-fragment is geen volledige productie-`.env`.

Als Git stopt wegens lokale wijzigingen, bekijk eerst `git status --short` en
bijvoorbeeld `git diff -- frontend/src/main.jsx`. Bewaar een bekende serveraanpassing
zo nodig apart voordat je opnieuw pullt:

```bash
git stash push -m "Serverwijziging voor Entra-update" -- frontend/src/main.jsx
git pull --ff-only
```

Dit voorbeeld bewaart alleen dat frontendbestand. Het wist geen wijzigingen en
neemt `.env` niet mee. Zet de stash niet blind terug: vergelijk de serveraanpassing
eerst met de nieuwe code.

### Bij alleen een gewijzigde `.env`

De API leest de configuratie bij het starten. Alleen `docker compose restart`
leest gewijzigde `env_file`-waarden niet opnieuw in; hermaak de container:

```bash
cd /opt/Q-Central/deploy
docker compose -f docker-compose.production.yml up -d --force-recreate api
```

Zijn ook de publieke hostnaam of Caddy-instellingen gewijzigd, hermaak dan Caddy
mee met `up -d --force-recreate api caddy`. Alleen een Entra-roltoewijzing of
redirect-URI in het Entra-portaal aanpassen vereist geen containerherstart;
start daarna wel een nieuwe login vanuit Q-Central.

### Acceptatiecontrole

```bash
curl -fsS https://central.q-home.be/api/auth/config
```

Verwacht:

```json
{"provider":"entra","configured":true}
```

`configured: true` betekent **alleen** dat tenant-ID, client-ID en secret zijn
ingevuld. Het test niet of de secret klopt, de redirect geregistreerd is, of de
gebruiker een rol heeft. Open het dashboard en voer een echte login uit.

| Controle | Verwacht resultaat |
| --- | --- |
| Lid van SG-PORTAL-Admins met Portal.Admin-toewijzing voor Q-Central | Dashboard opent |
| Geldig Microsoft-account zonder passende Q-Central-toewijzing | Geen applicatietoegang |
| Portal.User zonder beheerdersrol | Geen applicatietoegang |
| Verkeerde tenant/client of ongeldig token | Geen applicatiesessie |
| Afmelden en opnieuw een beveiligde API openen | Zonder andere credentials: 401 |
| Sessie verlopen | Opnieuw aanmelden; geen stille verlenging |
| Groepslidmaatschap/rol wijzigen | Nieuwe login haalt nieuwe claims op |

Een echte tenanttest kan niet door lokale tests vervangen worden.

## 5. Problemen oplossen

De browsermelding **“Microsoft-login mislukt of geen Q-Central-toegang”** is
algemeen. Bekijk na één nieuwe loginpoging de vaste diagnosecode op de server:

```bash
cd /opt/Q-Central/deploy
docker compose -f docker-compose.production.yml logs --since=5m api | grep 'Entra login failed'
```

Zonder treffers: controleer of de API de nieuwe code draait en bekijk dezelfde logs
zonder `grep`. Een fout op de Microsoft-pagina bereikt de callback mogelijk niet.
De eigen foutlogging bevat een vaste reden en foutklasse; geen ruwe Microsoft-
foutbeschrijving, secret of token. Deel voor diagnose alleen de betreffende
`Entra login failed`-regel. Algemene proxy-/accesslogs kunnen callback-URL's met
tijdelijke autorisatiecodes bevatten.

| Fout/melding | Betekenis | Actie |
| --- | --- | --- |
| `AADSTS500113` / No reply address | Redirect ontbreekt bij de gebruikte appregistratie | Registreer de exacte callback onder Authentication → Web; `.env` alleen is onvoldoende |
| `AADSTS50011` | Redirect komt niet overeen | Vergelijk volledig domein, HTTPS, pad en hoofdletters met de automatisch berekende callback |
| `AADSTS700016` / Application not found | App-ID niet gevonden in de gekozen tenant | Controleer tenant-ID en Application (client) ID; Geheim-id is geen client-ID |
| `missing_qcentral_role` | ID-token gecontroleerd, maar geen geaccepteerde app-rol; geen groepsalternatief ingesteld | Controleer Portal.Admin als exacte Value en de groepstoewijzing bij de Q-Central Enterprise Application; controleer of de Portal.Admin-code is gedeployd |
| `invalid_client` | Microsoft weigert de appcredentials | Secret-value, vervaldatum en bijbehorende appregistratie controleren; API na `.env`-wijziging hermaken |
| `invalid_grant` | Autorisatiecode is niet meer bruikbaar of de uitwisseling faalt | Nieuwe login starten; geen callback verversen of hergebruiken |
| `mismatching_state` | Aanmeldpoging ontbreekt, verlopen of past niet bij de browsercookie | Opnieuw via de Microsoft-knop starten; cookies toestaan en hetzelfde domein gebruiken |
| `id_token_validation_failed` | Handtekening of claims ongeldig | Bekijk foutklasse; controleer tenant, audience/configuratie en serverklok; schakel validatie niet uit |
| `incorrect_tenant` / `invalid_object_id` | Identiteitsclaim wijkt af of ontbreekt | Tenant/appconfiguratie en ontvangen claimtype onderzoeken |
| `invalid_roles_claim` | `roles` is geen lijst | Token-/claimconfiguratie controleren |
| `missing_id_token` / `expired_id_token` | ID-token ontbreekt of is verlopen | Nieuwe login; bij herhaling appconfiguratie en klok controleren |
| `microsoft_request_failed` | HTTP-verzoek naar Microsoft mislukt | Uitgaand HTTPS, DNS en beschikbaarheid controleren |
| `access_denied`, `unauthorized_client`, `invalid_request`, `oauth_failed`, `invalid_login_response` | Overige OAuth- of responsefout | Entra-aanmeldlog en de vaste foutklasse onderzoeken; geen tokens/secrets delen |
| `configured: false` | Minstens één Entra-instelling ontbreekt | Het daadwerkelijk gebruikte deploy/.env controleren en API hermaken |

**Entra meldt succes, maar Q-Central weigert:** authenticatie en applicatietoegang
zijn aparte controles. `missing_qcentral_role` bewijst dat de code het ID-token al
heeft geverifieerd. Het bewijst niet dat `Portal.Admin` is meegestuurd. Corrigeer de
roltoewijzing of deploy de code die deze rol accepteert; verander niet willekeurig
client-ID, tenant-ID of secret.

## 6. Optioneel: directe controle op groeps-ID

Sla deze sectie over voor de standaardaanpak met `Portal.Admin`. Dit alternatief
controleert een expliciete allowlist van groepsobject-ID's in de gecontroleerde
`groups`-claim van het ID-token. Het vereist geen nieuwe Q-Central-app-rol.

```dotenv
Q_CENTRAL_ENTRA_ADMIN_GROUP_IDS=<Object ID van SG-PORTAL-Admins>
Q_CENTRAL_ENTRA_SUPERADMIN_GROUP_IDS=
```

Gebruik exacte UUID's, gescheiden door komma's. Groepsnamen en wildcards worden
niet als configuratie geaccepteerd. Laat superadmin leeg tenzij een bepaalde groep
die rol moet krijgen. De hoogste passende rol geldt. App-rollen blijven toegang
verlenen wanneer dit alternatief is ingesteld; het is een aanvullende route.

Configureer **App registrations → Q-Central → Token configuration → Add groups
claim** voor het **ID-token**, met **Group ID** als waarde. Kies bij voorkeur
**Groups assigned to the application** en wijs de groep toe bij **Enterprise
applications → Q-Central → Users and groups**. Zonder gedefinieerde app-rollen is
Default Access voor die toewijzing voldoende: de API bepaalt de rol via de
allowlist. Zorg voor direct groepslidmaatschap en laat Assignment required op Yes.
Stuur groeps-ID's in `groups`, niet groepsnamen en niet via “emit groups as roles”.

| Diagnosecode | Actie |
| --- | --- |
| `missing_groups_claim` | Laat Entra de groups-claim in het ID-token meesturen |
| `unmatched_entra_group` | Vergelijk Object ID van de groep met de allowlist en het groepslidmaatschap |
| `invalid_groups_claim` | Configureer een lijst met groeps-ID's; geen namen of andere claimindeling |
| `groups_overage` | Entra laat groepsinformatie weg vanwege de tokenlimiet; beperk tot toegewezen groepen of gebruik app-rollen |

Er wordt geen Graph-opvraag gedaan bij overage en geen URL uit een claim gevolgd.
Een ontbrekende of niet-passende groep verleent geen toegang. Zie
[Microsoft: groepsclaims en app-rollen](https://learn.microsoft.com/security/zero-trust/develop/configure-tokens-group-claims-app-roles).

## 7. Werking, sessies en beheer

```mermaid
sequenceDiagram
    participant B as Browser
    participant Q as Q-Central API
    participant E as Microsoft Entra ID
    B->>Q: GET /api/auth/entra/login
    Q-->>B: Redirect met state, nonce en PKCE-challenge
    B->>E: Microsoft-login, MFA/Conditional Access
    E-->>B: Redirect naar geregistreerde callback met code
    B->>Q: GET /api/auth/entra/callback
    Q->>E: Code uitwisselen met client secret en PKCE-verifier
    E-->>Q: Tokens
    Q->>Q: ID-token en applicatietoegang controleren
    alt Passende rol of ingestelde groep
        Q-->>B: Q-Central-sessiecookie en redirect naar dashboard
    else Geweigerd
        Q-->>B: Algemene foutmelding; vaste diagnosecode in API-log
    end
```

De API gebruikt Authlib voor single-tenant OIDC Authorization Code Flow met PKCE
S256, state en nonce. De library controleert handtekening, issuer, audience en
levensduur. Q-Central vereist daarnaast een geldige tenant/object-identiteit,
`exp`/`nbf` en een toegelaten rol of ingestelde groep. De gevraagde scopes zijn
`openid profile email`; de code vraagt geen Microsoft Graph-scopes aan.

| Onderdeel | Huidig gedrag |
| --- | --- |
| Identiteit | `entra:<tenant-ID>:<object-ID>`; e-mail is geen primaire sleutel |
| Gebruikerstabel | Naam, e-mail, rol en laatste login worden bij een geldige login bijgewerkt; geen directorybrede synchronisatie |
| Tijdelijke flow | Ondertekende, leesbare HttpOnly/Secure/SameSite=Lax-cookie `qcentral_oidc`, maximaal 10 minuten; geen Microsoft-tokens erin |
| Applicatiesessie | Ondertekende HS256-JWT in HttpOnly/Secure/SameSite=Strict-cookie `qcentral_session` |
| Sessieduur | Maximaal ENTRA_SESSION_MINUTES, resterende ID-tokenlevensduur en de algemene SESSION_MINUTES-limiet, afhankelijk van wat het kortst is |
| Vernieuwen | Geen automatische verlenging of refresh-tokenflow |
| Microsoft-tokens | Worden bij de callback verwerkt; niet als browsersessie of in de gebruikerstabel opgeslagen |
| Afmelden | Wist de Q-Central-cookie; Microsoft SSO-sessie blijft beschikbaar |
| Rollen wijzigen | Nieuwe login leest nieuwe rollen/groepen; bestaande sessies kunnen tot vervaldatum blijven werken |
| Revocatie | Geen server-side sessieregister/Graph-revocatie; een gekopieerde sessie-JWT kan tot vervaldatum geldig blijven, ook na afmelden |
| MFA | Wordt door Entra-beleid afgedwongen; Q-Central toont “beheerd in Entra” en beweert niet dat elke login MFA uitvoerde |
| Accountbeheer | Aanmaken en wijzigen van accounts, rollen en wachtwoorden via Q-Central is in Entra-modus geblokkeerd |
| Audit | `entra_login_success`, `entra_login_failed` met vaste reden; afmelden wordt apart vastgelegd |
| Machinekoppelingen | Q-Box-agenttokens en Q-Portal-token blijven hun eigen authenticatie gebruiken |

De overeenkomst met Cohvera betreft de login via Microsoft en de app-rol
`Portal.Admin`. Q-Central gebruikt eigen sessiecode; het is geen kopie van Cohvera's
server-side sessieopslag of bedrijfsautorisatie.

Voor incidentele handmatige API-calls accepteert de API ook de Q-Central-sessie-JWT
als Bearer-token. Gebruik daarvoor `Q_CENTRAL_SESSION_TOKEN` in create-serial.sh of
`QCENTRAL_SESSION_TOKEN` in de curl-documentatie. Dit is de tijdelijke waarde van
`qcentral_session`, **geen Microsoft ID-/access-token**. Bewaar die niet in Git of
productie-.env; gebruik voor normaal beheer het dashboard.

Lokale wachtwoordlogin bestaat alleen bij expliciet `Q_CENTRAL_AUTH_MODE=local`
met een geldige `Q_CENTRAL_ADMIN_CREDENTIAL_HASH`. Sessies uit de andere modus worden
geweigerd. In Entra-modus blijven lokale wachtwoordlogin en lokaal accountbeheer
geblokkeerd, ook als oude admininstellingen in het bestand staan.

## 8. Ontwikkeling en tests

Voer uit met Python 3.12 en de dependencies uit `backend/requirements.txt`, zoals
in de backend-container:

```bash
PYTHONPATH=backend python -m unittest discover -s backend/tests
```

De tests gebruiken een geïsoleerde database, lokaal ondertekende ID-tokens en
nagebootste Microsoft-endpoints. Ze controleren onder meer PKCE, nonce/state,
signature/issuer/audience/tenant, vervaldatum, exacte rollen, groepsallowlists,
rolwijzigingen bij opnieuw aanmelden, afmelden, blokkering van lokale wijzigingen
en diagnosecodes zonder gevoelige upstream-teksten. Ze bewijzen geen geslaagde
login met de productie-appregistratie; voer daarvoor de acceptatiecontrole uit.

| Bestand | Verantwoordelijkheid |
| --- | --- |
| `backend/qcentral/entra.py` | OIDC-client, callbacks, rol/groepscontrole en diagnosecodes |
| `backend/qcentral/config.py` | Instellingen, validatie en berekening van callback-URL |
| `backend/qcentral/security.py` | Aanmaken/valideren van Q-Central-sessies en providercontrole |
| `backend/qcentral/main.py` | Middleware, routers, profiel, accountbeheer en logout |
| `frontend/src/main.jsx` | Loginconfiguratie ophalen, Microsoft-knop en foutmelding |
| `deploy/caddy/Caddyfile` | Publieke /api-routes naar de backend, met prefix stripping |
| `backend/tests/test_entra.py` | Auth-tests zonder echte Microsoft-tenant |

De API biedt zowel `/api/auth/*` als `/auth/*`-varianten voor de proxy. De publiek
geregistreerde callback blijft `/api/auth/entra/callback`. Authlib en Starlette
verwerken de tijdelijke flowcookie; de proxy moet cookies en queryparameters
correct doorgeven.

Bronnen: [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow),
[Microsoft app-rollen](https://learn.microsoft.com/entra/identity-platform/howto-add-app-roles-in-apps),
[Authlib Starlette OIDC](https://docs.authlib.org/en/v1.6.11/client/starlette.html).
