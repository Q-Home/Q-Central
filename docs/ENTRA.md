# Microsoft Entra ID voor Q-Central

Q-Central gebruikt standaard Entra, zoals Cohvera: single-tenant OpenID Connect,
Authorization Code Flow met PKCE, nonce en state. Authlib controleert de handtekening,
issuer, audience en geldigheidsduur. Daarna controleert Q-Central de tenant, object-ID
en exacte app-rollen of expliciet ingestelde groeps-ID's. Er worden geen
Graph-rechten gevraagd.

Registreer een **Web**-app voor Q-Central binnen dezelfde organisatietenant als
Cohvera. Gebruik een eigen client-ID en serversecret. Kopieer geen Cohvera-secret.
Voor dezelfde beheerdersaanpak als Cohvera accepteert Q-Central de exacte app-rol
`Portal.Admin` als lokale admin. De toewijzing moet bij de Q-Central Enterprise
Application gebeuren; een rol op alleen de Cohvera-app geeft geen Q-Central-toegang.

1. Stel de Web redirect URI exact in op
   `https://central.q-home.be/api/auth/entra/callback` (of dezelfde route onder de
   ingestelde `Q_CENTRAL_EXTERNAL_URL`). De bestaande Caddy-router ondersteunt dit.
2. Voor dezelfde aanpak als Cohvera: maak bij **App registrations → Q-Central →
   App roles** een rol met exacte **Value** `Portal.Admin`, toegestaan voor
   Users/Groups en ingeschakeld. Wijs bij **Enterprise applications → Q-Central →
   Users and groups** de bestaande groep `SG-PORTAL-Admins` toe aan die rol.
   Zet **Assignment required = Yes**. Bestaande `QCentral.Admin` en
   `QCentral.SuperAdmin`-rollen blijven ondersteund. De groeps-ID-koppeling
   hieronder is een optioneel alternatief, geen vereiste voor de Cohvera-aanpak.
3. Stel MFA en Conditional Access in Entra in. Zet implicit en public-client flows uit.
4. Vul onderstaande waarden in de niet-gecommitteerde productie-`.env` in en
   bouw/herstart de API en frontend via de normale deployprocedure.

```dotenv
Q_CENTRAL_AUTH_MODE=entra
Q_CENTRAL_EXTERNAL_URL=https://central.q-home.be
Q_CENTRAL_ENTRA_TENANT_ID=<Directory Tenant ID>
Q_CENTRAL_ENTRA_CLIENT_ID=<Q-Central Application Client ID>
Q_CENTRAL_ENTRA_CLIENT_SECRET=<Client secret VALUE>
Q_CENTRAL_ENTRA_SESSION_MINUTES=15
```

Het secret blijft bij de API. Roteer dit voor vervaldatum. Gebruik HTTPS, ook voor
lokale Entra-tests, en registreer de exacte testcallback afzonderlijk.
Zonder complete configuratie geeft de loginpagina een configuratiemelding; er is
geen automatische terugval op lokale wachtwoorden.

## Bestaande Cohvera-groepen gebruiken

Als alternatief voor Q-Central-app-rollen kan de API de bestaande groep
`SG-PORTAL-Admins` controleren via de `groups`-claim in het gecontroleerde ID-token.
Vul de **Object ID van de groep** in, geen client-ID, tenant-ID of groepsnaam:

```dotenv
Q_CENTRAL_ENTRA_ADMIN_GROUP_IDS=<Object ID van SG-PORTAL-Admins>
Q_CENTRAL_ENTRA_SUPERADMIN_GROUP_IDS=
```

Meerdere object-ID's worden gescheiden door komma's. Laat superadmin leeg tenzij
een specifieke groep die rol hoort te krijgen. Gebruik voor die groep dezelfde
instelling met `SUPERADMIN` in plaats van `ADMIN`. De hoogste passende rol geldt.
De oorspronkelijke Q-Central-app-rollen blijven ook toegang verlenen.

Configureer in **App registrations → Q-Central → Token configuration → Add groups
claim** de groepsclaim voor het **ID-token**, met **Group ID** als waarde. Kies
bij voorkeur **Groups assigned to the application** en wijs de bestaande groep
toe bij **Enterprise applications → Q-Central → Users and groups**. Zonder eigen
app-rollen is Default Access voldoende voor deze groepstoewijzing; de API bepaalt
de rol via de ingestelde groeps-ID. Zorg voor direct groepslidmaatschap.
Stuur groepen als `groups`, niet als `roles` of groepsnamen. Laat Assignment
required op Yes staan. Deze Entra-instelling kan de applicatiecode niet zelf wijzigen.

De API geeft alleen toegang bij een exacte match met een ingestelde groeps-ID.
Zonder passende rol of groep blijft de login geweigerd. Bij ontbrekende groepsclaims
of group overage wordt geen toegang gegokt en geen ongeteste Graph-URL gevolgd.
Beperk in dat geval de uitgestuurde groepen of gebruik app-rollen. Bestaande
sessies behouden hun geldigheid tot de eerder beschreven vervaldatum.

Zie [Microsoft: groepsclaims en app-rollen configureren](https://learn.microsoft.com/security/zero-trust/develop/configure-tokens-group-claims-app-roles).

`Portal.Admin` en `QCentral.Admin` geven admin-toegang; `QCentral.SuperAdmin`
geeft superadmin-toegang. `Portal.User` geeft geen toegang tot het beheerplatform.
De bestaande API heeft geen
volledige fijnmazige autorisatie voor support/installateurs/lezers; daarom worden
die rollen niet automatisch toegelaten via Entra.

Een gebruiker wordt geïdentificeerd door tenant-ID plus object-ID, niet e-mail.
De lokale gebruikerstabel toont de bij de laatste login ontvangen naam en rol.
Account-, wachtwoord- en rolwijzigingen via de API zijn in Entra-modus geblokkeerd.
MFA wordt als 'beheerd in Entra' getoond; Q-Central beweert niet dat iedere login
MFA heeft uitgevoerd. Tijdelijke OIDC-flowgegevens zitten maximaal tien minuten
in een Secure, HttpOnly, SameSite=Lax-cookie; tokens worden niet daarin opgeslagen.
De applicatiesessie zit in een aparte Secure, HttpOnly, SameSite=Strict-cookie en
vervalt na maximaal de ingestelde duur (standaard 15 minuten) of eerder bij het
vervallen van het ID-token. Er is geen automatische verlenging. Afmelden wist de
Q-Central-cookie; de Microsoft SSO-sessie blijft beschikbaar voor andere apps.
Entra-wijzigingen worden bij een nieuwe login opgehaald. Bestaande sessies blijven
tot hun vervaldatum geldig; directe Entra-revocatie via Graph is niet geïmplementeerd.

Lokale authenticatie is alleen expliciet beschikbaar met `Q_CENTRAL_AUTH_MODE=local`
en een geldige `Q_CENTRAL_ADMIN_CREDENTIAL_HASH`. Sessies uit de andere modus worden
geweigerd, inclusief bestaande lokale sessies zodra Entra actief is. Q-Box-agent-
en Q-Portal-tokenauthenticatie blijven afzonderlijke machinekoppelingen.

Voor handmatige API-calls kunnen de scripts een tijdelijk `Q_CENTRAL_SESSION_TOKEN`
gebruiken: de waarde van de `qcentral_session`-cookie na een geslaagde login.
De curl-voorbeelden gebruiken daarvoor `QCENTRAL_SESSION_TOKEN`. Dit is een
kortlevende Q-Central-sessie, geen Microsoft access- of ID-token. Bewaar deze niet
in productie-`.env` en commit deze niet; gebruik voor beheer bij voorkeur het dashboard.

Validatie: `PYTHONPATH=backend python -m unittest discover -s backend/tests`.
Test daarna met de echte tenant: bevoegde beheerder, gebruiker zonder app-rol,
verkeerde tenant, verlopen sessie en afmelden. Een echte Microsoft-login vereist
de bovenstaande externe configuratie.

Bij een mislukte login blijft de browsermelding algemeen. De API-log en het
audit-event `entra_login_failed` bevatten wel een vaste diagnosecode, zonder tokens,
secrets of ruwe Microsoft-foutbeschrijvingen. Bekijk na een nieuwe poging:

```bash
cd /opt/Q-Central/deploy
docker compose -f docker-compose.production.yml logs --since=5m api
```

- `missing_qcentral_role`: geldig gecontroleerd ID-token, maar geen exacte
  `Portal.Admin`/`QCentral.Admin`/`QCentral.SuperAdmin`-rol. Controleer app-role Values en de
  toewijzing van de bestaande groep aan de Q-Central Enterprise Application.
- `missing_groups_claim`: groeps-ID's zijn ingesteld, maar Entra stuurt geen
  `groups` mee in het ID-token. Configureer de groepsclaim voor Q-Central.
- `unmatched_entra_group`: geen token-groep komt overeen met de ingestelde object-ID's.
- `invalid_groups_claim`: groepsclaims bevatten geen lijst met geldige object-ID's.
- `groups_overage`: Entra heeft groepsinformatie weggelaten wegens de tokenlimiet;
  beperk de groepen tot de toegewezen groepen of gebruik app-rollen.
- `invalid_client`: Microsoft weigert de appcredentials. Controleer dat client-ID
  en secret-value bij dezelfde appregistratie horen en dat het secret geldig is.
- `mismatching_state`: start een nieuwe login vanuit Q-Central, met cookies toegestaan.
- `id_token_validation_failed`: controle van handtekening/claims mislukt; onderzoek
  de configuratie en serverklok. De foutklasse staat naast de diagnosecode.

Protocol: [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).
Library: [Authlib Starlette OIDC](https://docs.authlib.org/en/latest/client/starlette.html).
