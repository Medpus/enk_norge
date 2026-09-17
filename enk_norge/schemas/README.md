# SAF-T Financial-skjema

`Norwegian_SAF-T_Financial_Schema_v_1.40.xsd` er Skatteetatens uendrede XML-skjema,
versjon 1.40 med revisjonsdato 2026-04-30. Opphavsrettsangivelsen i skjemaet er bevart.
Det eksterne skjemaet omfattes ikke av appens egen MIT-lisens.

Kilden er [Skatteetatens SAF-T-repo](https://github.com/Skatteetaten/saf-t/tree/05179521e435d82feb0b2d6c89a92a32a4f2d02f/SAF-T_Financial_1.4).
SHA-256 for fila:

```
0e2f33c825612ea45f991b4a04039c63eae070df7da10fecab18fd043d4f2128
```

Appen bruker skjemaet til lokal validering. XSD-validering kontrollerer formatet;
integrasjonstestene kontrollerer også beløp, kontoer og sammenheng med hovedboken.
