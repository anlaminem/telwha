(function () {
    const form = document.getElementById('contactForm');
    if (!form) return;

    form.addEventListener('submit', (event) => {
        event.preventDefault();

        const lang = document.documentElement.lang;
        const messageByLang = {
            uk: 'Форма відправлена (далі можна підключити Telegram-бота або бекенд).',
            en: 'Form submitted (you can now connect a Telegram bot or backend).',
            es: 'Formulario enviado (ahora puedes conectar un bot de Telegram o backend).'
        };

        alert(messageByLang[lang] || messageByLang.uk);
    });
})();
