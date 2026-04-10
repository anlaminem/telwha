(function () {
  const form = document.getElementById('contactForm');
  const status = document.getElementById('formStatus');
  if (!form || !status) return;

  const formStartedAt = Date.now();
  const lang = (document.documentElement.lang || 'uk').toLowerCase();

  const messages = {
    uk: {
      sending: 'Надсилаємо...',
      success: 'Дякуємо за запит! Протягом 24 годин зв’яжемось і почнемо працювати над досягненням вашої цілі.',
      genericError: 'Не вдалося надіслати запит. Спробуйте ще раз.',
      networkError: 'Сталася помилка. Спробуйте ще раз.',
      validationFail: 'Запит не пройшов перевірку.',
      tooFast: 'Будь ласка, заповніть форму уважно і спробуйте ще раз.',
      badName: 'Вкажіть ім’я.',
      badContact: 'Вкажіть коректний телефон, email або Telegram.',
      badMessage: 'Опишіть запит трохи детальніше.'
    },
    en: {
      sending: 'Sending...',
      success: 'Thank you for your request! Within 24 hours we will get in touch and start working on achieving your goal.',
      genericError: 'Could not send your request. Please try again.',
      networkError: 'An error occurred. Please try again.',
      validationFail: 'Your request did not pass validation.',
      tooFast: 'Please fill out the form carefully and try again.',
      badName: 'Please enter your name.',
      badContact: 'Enter a valid phone number, email, or Telegram.',
      badMessage: 'Please describe your request in a bit more detail.'
    },
    es: {
      sending: 'Enviando...',
      success: 'Gracias por tu solicitud. En un plazo de 24 horas nos pondremos en contacto contigo y comenzaremos a trabajar para alcanzar tu objetivo.',
      genericError: 'No se pudo enviar tu solicitud. Inténtalo de nuevo.',
      networkError: 'Ocurrió un error. Inténtalo de nuevo.',
      validationFail: 'Tu solicitud no pasó la validación.',
      tooFast: 'Por favor, completa el formulario con atención e inténtalo de nuevo.',
      badName: 'Por favor, indica tu nombre.',
      badContact: 'Indica un teléfono, email o Telegram válido.',
      badMessage: 'Describe tu solicitud con un poco más de detalle.'
    }
  };

  const t = messages[lang] || messages.uk;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();

    const submitButton = form.querySelector('button[type="submit"]');
    const originalButtonText = submitButton.textContent;

    const name = form.name.value.trim();
    const contact = form.contact.value.trim();
    const message = form.message.value.trim();
    const honey = form._honey ? form._honey.value.trim() : '';

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/i;
    const telegramRegex = /^@?[a-zA-Z0-9_]{5,32}$/;
    const phoneRegex = /^\+?[0-9()\-\s]{8,20}$/;

    const spamWords = [
      'seo',
      'casino',
      'viagra',
      'backlinks',
      'guest post',
      'loan',
      'escort',
      'crypto recovery'
    ];

    const secondsSpent = (Date.now() - formStartedAt) / 1000;
    const hasUrl = /https?:\/\/|www\./i.test(message);
    const hasSpamWord = spamWords.some(word => message.toLowerCase().includes(word));
    const validContact =
      emailRegex.test(contact) ||
      telegramRegex.test(contact) ||
      phoneRegex.test(contact);

    status.style.display = 'none';
    status.textContent = '';

    if (honey) {
      status.textContent = t.validationFail;
      status.style.display = 'block';
      return;
    }

    if (secondsSpent < 4) {
      status.textContent = t.tooFast;
      status.style.display = 'block';
      return;
    }

    if (name.length < 2) {
      status.textContent = t.badName;
      status.style.display = 'block';
      return;
    }

    if (!validContact) {
      status.textContent = t.badContact;
      status.style.display = 'block';
      return;
    }

    if (message.length < 10) {
      status.textContent = t.badMessage;
      status.style.display = 'block';
      return;
    }

    if (hasUrl || hasSpamWord) {
      status.textContent = t.validationFail;
      status.style.display = 'block';
      return;
    }

    submitButton.disabled = true;
    submitButton.textContent = t.sending;

    const formData = {
      name,
      contact,
      message,
      _subject: 'New request from TELWHA website',
      _template: 'table',
      _captcha: 'false',
      _honey: honey
    };

    try {
      const response = await fetch('https://formsubmit.co/ajax/03332dc75a327051891e5e1b805e2418', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      const result = await response.json();

      if (result.success === 'true' || result.success === true) {
        form.reset();
        status.textContent = t.success;
        status.style.display = 'block';
      } else {
        status.textContent = t.genericError;
        status.style.display = 'block';
      }
    } catch (error) {
      status.textContent = t.networkError;
      status.style.display = 'block';
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = originalButtonText;
    }
  });
})();