# Scopo della repository
Questa repository ha lo scopo di raccogliere e organizzare la lista di appunti, formulari e soluzioni di esercizi per il CdL di Informatica di Tor Vergata.

Né la repository né il server per il sito [Lab25a](http://lab25a.it:8000) terranno una copia dei contenuti, ma fungeranno da interfaccia per gli studenti che vogliono offrire e usufruire di tali materiali. La partecipazione è libera ma molto gradita.

## Contribuire
Per ogni release viene pubblicato un solo file (PDF o ZIP). Se hai più materiali, creali come release separate oppure raggruppali in un unico ZIP.

### Formato per tutto il materiale in un'unica release
Per aggiungere il proprio materiale alla repository è possibile effettuare una pull request in cui si aggiungono nel file `repos.json` le informazioni relative ai contenuti. In particolare si forniscano i dati seguenti:

1.  title
2.  description
3.  type ("Appunti", "Esercizi", "Soluzioni", "Formulari")
4.  link_repository 
5.  course
6.  tags

Gli attributi *2* e *6* sono facoltativi e possono essere omessi.

Un esempio di *entry* ben definita:
``` 
{
        "title": "Architettura degli Elaboratori - Formulario",
        "description": "Pipeline, cache, gerarchia di memoria e prestazioni: formule essenziali.",
        "type": "formulari",
        "link_repository": "https://github.com/...",
        "course": "Architettura degli Elaboratori",
        "tags": ["pipeline", "cache"]
}
```


### Formato per tutto il materiale in più releases
Fornendo il link della repository verranno aggiunti tutti e soli i materiali dell'ultima **Release**, nel caso si volessero caricare più materiali della stessa repository vanno aggiunti più oggetti. 

Un esempio 
```
{
        "title": "Architettura degli Elaboratori - Formulario",
        "description": "Pipeline, cache, gerarchia di memoria e prestazioni: formule essenziali.",
        "type": "formulari",
        "link_release": "https://github.com/.../releases/...",
        "course": "Architettura degli Elaboratori",
        "tags": ["pipeline", "cache"]
}
```

Sono accettati solo URL nella forma:

- `https://github.com/<owner>/<repo>/releases/tag/<tag>`   → release specifica
- `https://github.com/<owner>/<repo>/releases/latest`      → ultima release

**Non** sono accettati link di download diretto degli asset
(`/releases/download/<tag>/<file>`): in quel caso l'entry viene
pubblicata senza file. Per un asset specifico, crea una release
dedicata e usa il link `/releases/tag/<tag>`.

In questo caso verranno aggiunti all'archivio solo i materiali specificati dalla Release.

### Struttura dei contenuti
La repository aggiunta può avere qualsiasi struttura si preferisca, ma per la pubblicazione è necessario che abbia una visibilità pubblica e contenga almeno una **Release** contenente il materiale da pubblicare (in formato zip o pdf). Si consiglia la lettura [Come creare una release su GitHub](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)