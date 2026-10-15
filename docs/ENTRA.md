# Microsoft Entra ID voor Q-Central

Q-Central gebruikt standaard Entra, zoals Cohvera: single-tenant OpenID Connect,
Authorization Code Flow met PKCE, nonce en state. Authlib controleert de handtekening,
issuer, audience en geldigheidsduur. Daarna controleert Q-Central de tenant, object-ID
en exacte app-rollen. Er worden geen Graph-rechten gevraagd.

Registreer een **Web**-app voor Q-Central binnen dezelfde organisatietenant als
Cohvera. Gebruik een eigen client-ID en serversecret. Kopieer geen Cohvera-secret
en gebruik geen Portal.Admin-toewijzing als Q-Central-toegang.

1. Stel de Web redirect URI exact in op
   `https://central.q-home.be/api/auth/entra/callback` (of dezelfde route onder de
   ingestelde `Q_CENTRAL_EXTERNAL_URL`). De bestaande Caddy-router ondersteunt dit.
2. Maak app-rollen met exacte waarden `QCentral.Admin` en `QCentral.SuperAdmin`,
   toegestaan voor Users/Groups. Wijs bevoegde medewerkers/groepen toe via de
   Enterprise Application en zet **Assignment required = Yes**.
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

Beide rollen krijgen toegang tot het control plane. De bestaande API heeft geen
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
  `QCentral.Admin`/`QCentral.SuperAdmin`-rol. Controleer app-role Values en de
  toewijzing van de bestaande groep aan de Q-Central Enterprise Application.
- `invalid_client`: Microsoft weigert de appcredentials. Controleer dat client-ID
  en secret-value bij dezelfde appregistratie horen en dat het secret geldig is.
- `mismatching_state`: start een nieuwe login vanuit Q-Central, met cookies toegestaan.
- `id_token_validation_failed`: controle van handtekening/claims mislukt; onderzoek
  de configuratie en serverklok. De foutklasse staat naast de diagnosecode.

Protocol: [Microsoft authorization code flow](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow).
Library: [Authlib Starlette OIDC](https://docs.authlib.org/en/latest/client/starlette.html).
